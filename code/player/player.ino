/*
  Soupocalypse player node.

  Hardware:
    ESP32
    MPU6050 on I2C SDA=21, SCL=22, address 0x68
    QMC5883L magnetometer on same I2C bus, typical address 0x0D
    Optional SSD1306 OLED on same I2C bus, typical address 0x3C
    Health LEDs: GPIO 32, 33, 25, 26, 27
    FX LEDs: GPIO 16, 17, 18, 19
    Recenter/calibrate button: GPIO23 to GND

  Change PLAYER_ID to 101 or 102 before uploading to each controller.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

#if __has_include(<Adafruit_GFX.h>) && __has_include(<Adafruit_SSD1306.h>)
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#define HAS_OLED 1
#else
#define HAS_OLED 0
#endif

#define PLAYER_ID 101

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define MPU6050_ADDR 0x68
#define QMC5883L_ADDR 0x0D
#define OLED_ADDR 0x3C

const uint8_t HEALTH_LED_PINS[5] = {32, 33, 25, 26, 27};
const uint8_t FX_LED_PINS[4] = {16, 17, 18, 19};
const uint8_t RECENTER_BUTTON_PIN = 23;
const uint8_t ONBOARD_LED_PIN = 2;

#define WIFI_CHANNEL 6
const uint16_t PACKET_MAGIC = 0x51A7;
const uint8_t PACKET_TYPE_PLAYER = 20;
const uint8_t ACTION_NONE = 0;
const uint8_t ACTION_BEAM = 1;
const uint8_t ACTION_BUBBLE = 2;

const uint32_t STATUS_INTERVAL_MS = 55;
const uint32_t ACTION_LOCKOUT_MS = 420;
const uint32_t RECENTER_DEBOUNCE_MS = 50;

const float GESTURE_START_G = 0.34f;
const float GESTURE_END_G = 0.14f;
const uint32_t GESTURE_MIN_MS = 80;
const uint32_t GESTURE_MAX_MS = 620;
const uint32_t GESTURE_STILL_MS = 70;
const float BEAM_DOWN_ACCEL_G = -0.46f;
const float BUBBLE_UP_ACCEL_G = 0.46f;

uint8_t broadcastMac[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

#if HAS_OLED
Adafruit_SSD1306 display(128, 64, &Wire, -1);
#endif

struct __attribute__((packed)) PlayerPacket {
  uint16_t magic;
  uint8_t packetType;
  uint8_t playerId;
  uint16_t sequence;
  int16_t headingDeg10;
  uint8_t action;
  uint8_t flags;
  uint32_t uptimeMs;
};

uint16_t packetSequence = 0;
uint32_t lastStatusMs = 0;
uint32_t lastActionMs = 0;
uint32_t lastOledMs = 0;

bool mpuReady = false;
bool compassReady = false;
float headingDeg = 0.0f;
float headingOffsetDeg = 0.0f;

float accelX = 0.0f;
float accelY = 0.0f;
float accelZ = 1.0f;
float gravityX = 0.0f;
float gravityY = 0.0f;
float gravityZ = 1.0f;
float linearX = 0.0f;
float linearY = 0.0f;
float linearZ = 0.0f;
float linearMag = 0.0f;

bool gestureActive = false;
uint32_t gestureStartMs = 0;
uint32_t gestureLastMotionMs = 0;
float gesturePeakUp = 0.0f;
float gesturePeakDown = 0.0f;
float gesturePeakMag = 0.0f;

bool recenterLastRaw = HIGH;
bool recenterPressed = false;
uint32_t recenterChangedMs = 0;
uint32_t fxUntilMs = 0;
uint8_t lastAction = ACTION_NONE;

float normalizeDeg(float deg) {
  while (deg >= 180.0f) deg -= 360.0f;
  while (deg < -180.0f) deg += 360.0f;
  return deg;
}

void writeReg(uint8_t addr, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readRegs(uint8_t addr, uint8_t reg, uint8_t *buf, uint8_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  uint8_t got = Wire.requestFrom(addr, len);
  if (got != len) return false;
  for (uint8_t i = 0; i < len; i++) {
    buf[i] = Wire.read();
  }
  return true;
}

int16_t be16(uint8_t hi, uint8_t lo) {
  return (int16_t)((hi << 8) | lo);
}

int16_t le16(uint8_t lo, uint8_t hi) {
  return (int16_t)((hi << 8) | lo);
}

void setupMpu() {
  writeReg(MPU6050_ADDR, 0x6B, 0x00);
  delay(80);
  uint8_t who = 0;
  mpuReady = readRegs(MPU6050_ADDR, 0x75, &who, 1);
  Serial.print("MPU6050=");
  Serial.println(mpuReady ? "OK" : "MISSING");
}

void setupCompass() {
  writeReg(QMC5883L_ADDR, 0x0B, 0x01);
  writeReg(QMC5883L_ADDR, 0x09, 0x1D);  // continuous, 200Hz, 8G, OSR 512
  delay(20);
  uint8_t buf[6];
  compassReady = readRegs(QMC5883L_ADDR, 0x00, buf, 6);
  Serial.print("QMC5883L=");
  Serial.println(compassReady ? "OK" : "MISSING");
}

void updateMpu() {
  if (!mpuReady) return;
  uint8_t buf[14];
  if (!readRegs(MPU6050_ADDR, 0x3B, buf, 14)) return;
  accelX = (float)be16(buf[0], buf[1]) / 16384.0f;
  accelY = (float)be16(buf[2], buf[3]) / 16384.0f;
  accelZ = (float)be16(buf[4], buf[5]) / 16384.0f;
  const float alpha = 0.93f;
  gravityX = gravityX * alpha + accelX * (1.0f - alpha);
  gravityY = gravityY * alpha + accelY * (1.0f - alpha);
  gravityZ = gravityZ * alpha + accelZ * (1.0f - alpha);
  linearX = accelX - gravityX;
  linearY = accelY - gravityY;
  linearZ = accelZ - gravityZ;
  linearMag = sqrtf(linearX * linearX + linearY * linearY + linearZ * linearZ);
}

void updateCompass() {
  if (!compassReady) return;
  uint8_t buf[6];
  if (!readRegs(QMC5883L_ADDR, 0x00, buf, 6)) return;
  int16_t mx = le16(buf[0], buf[1]);
  int16_t my = le16(buf[2], buf[3]);
  if (mx == 0 && my == 0) return;
  float raw = atan2f((float)my, (float)mx) * 180.0f / PI;
  headingDeg = normalizeDeg(raw - headingOffsetDeg);
}

int16_t headingDeg10() {
  return (int16_t)roundf(headingDeg * 10.0f);
}

void sendPacket(uint8_t action) {
  PlayerPacket packet;
  packet.magic = PACKET_MAGIC;
  packet.packetType = PACKET_TYPE_PLAYER;
  packet.playerId = PLAYER_ID;
  packet.sequence = packetSequence++;
  packet.headingDeg10 = headingDeg10();
  packet.action = action;
  packet.flags = 1;
  packet.uptimeMs = millis();
  esp_now_send(broadcastMac, (uint8_t *)&packet, sizeof(packet));
  Serial.print("PLAYER_LOCAL,");
  Serial.print(PLAYER_ID);
  Serial.print(",");
  Serial.print(headingDeg, 1);
  Serial.print(",");
  Serial.print(action);
  Serial.print(",");
  Serial.println(packet.sequence);
}

void setFxLeds(uint8_t mask) {
  for (int i = 0; i < 4; i++) {
    digitalWrite(FX_LED_PINS[i], (mask & (1 << i)) ? HIGH : LOW);
  }
}

void triggerAction(uint8_t action) {
  uint32_t now = millis();
  if (now - lastActionMs < ACTION_LOCKOUT_MS) return;
  lastActionMs = now;
  lastAction = action;
  fxUntilMs = now + 300;
  sendPacket(action);
}

void startGesture(uint32_t now) {
  gestureActive = true;
  gestureStartMs = now;
  gestureLastMotionMs = now;
  gesturePeakUp = linearZ;
  gesturePeakDown = linearZ;
  gesturePeakMag = linearMag;
}

void updateGesture(uint32_t now) {
  gesturePeakUp = max(gesturePeakUp, linearZ);
  gesturePeakDown = min(gesturePeakDown, linearZ);
  gesturePeakMag = max(gesturePeakMag, linearMag);
  if (linearMag >= GESTURE_END_G) {
    gestureLastMotionMs = now;
  }
}

void finishGesture(uint32_t now) {
  uint32_t duration = now - gestureStartMs;
  if (duration >= GESTURE_MIN_MS && duration <= GESTURE_MAX_MS && gesturePeakMag >= GESTURE_START_G) {
    if (gesturePeakDown <= BEAM_DOWN_ACCEL_G && fabsf(gesturePeakDown) > fabsf(gesturePeakUp) * 0.85f) {
      triggerAction(ACTION_BEAM);
    } else if (gesturePeakUp >= BUBBLE_UP_ACCEL_G) {
      triggerAction(ACTION_BUBBLE);
    }
  }
  gestureActive = false;
}

void detectGestures() {
  uint32_t now = millis();
  if (!gestureActive) {
    if (linearMag >= GESTURE_START_G || fabsf(linearZ) >= GESTURE_START_G) {
      startGesture(now);
    }
    return;
  }
  updateGesture(now);
  bool still = now - gestureLastMotionMs >= GESTURE_STILL_MS && now - gestureStartMs >= GESTURE_MIN_MS;
  bool timeout = now - gestureStartMs >= GESTURE_MAX_MS;
  if (still || timeout) {
    finishGesture(now);
  }
}

void calibrateHeading() {
  headingOffsetDeg += headingDeg;
  headingOffsetDeg = normalizeDeg(headingOffsetDeg);
  fxUntilMs = millis() + 700;
  Serial.print("HEADING_CAL,");
  Serial.println(headingOffsetDeg, 1);
}

void updateButton() {
  uint32_t now = millis();
  bool raw = digitalRead(RECENTER_BUTTON_PIN);
  if (raw != recenterLastRaw) {
    recenterLastRaw = raw;
    recenterChangedMs = now;
  }
  if (now - recenterChangedMs < RECENTER_DEBOUNCE_MS) return;
  bool pressed = raw == LOW;
  if (pressed && !recenterPressed) {
    calibrateHeading();
  }
  recenterPressed = pressed;
}

void updateLeds() {
  uint32_t now = millis();
  for (int i = 0; i < 5; i++) {
    digitalWrite(HEALTH_LED_PINS[i], HIGH);
  }
  if (now < fxUntilMs) {
    if (lastAction == ACTION_BEAM) {
      setFxLeds(0x0F);
    } else if (lastAction == ACTION_BUBBLE) {
      setFxLeds(1 << ((now / 65) % 4));
    } else {
      setFxLeds((now / 90) % 2 ? 0x0F : 0x00);
    }
    digitalWrite(ONBOARD_LED_PIN, (now / 80) % 2);
  } else {
    setFxLeds(0);
    digitalWrite(ONBOARD_LED_PIN, LOW);
  }
}

void updateOled() {
#if HAS_OLED
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("SOUP P");
  display.println(PLAYER_ID);
  display.setCursor(0, 16);
  display.print("Head ");
  display.print(headingDeg, 0);
  display.println(" deg");
  display.setCursor(0, 30);
  display.print("MPU ");
  display.print(mpuReady ? "OK" : "NO");
  display.print(" QMC ");
  display.println(compassReady ? "OK" : "NO");
  display.setCursor(0, 46);
  display.print("Swing: down beam/up bub");
  display.display();
#endif
}

void setupEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("ERR,ESP_NOW_INIT");
    delay(1000);
    ESP.restart();
  }
  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastMac, 6);
  peerInfo.channel = WIFI_CHANNEL;
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);
}

void setupDisplayAndLeds() {
  pinMode(RECENTER_BUTTON_PIN, INPUT_PULLUP);
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  for (int i = 0; i < 5; i++) pinMode(HEALTH_LED_PINS[i], OUTPUT);
  for (int i = 0; i < 4; i++) pinMode(FX_LED_PINS[i], OUTPUT);
#if HAS_OLED
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    display.clearDisplay();
    display.display();
  }
#endif
}

void setup() {
  Serial.begin(115200);
  delay(400);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Serial.println();
  Serial.println("Soupocalypse player");
  Serial.print("PLAYER_ID=");
  Serial.println(PLAYER_ID);
  setupDisplayAndLeds();
  setupMpu();
  setupCompass();
  setupEspNow();
  fxUntilMs = millis() + 600;
}

void loop() {
  uint32_t now = millis();
  updateMpu();
  updateCompass();
  updateButton();
  detectGestures();
  if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
    lastStatusMs = now;
    sendPacket(ACTION_NONE);
  }
  if (now - lastOledMs >= 160) {
    lastOledMs = now;
    updateOled();
  }
  updateLeds();
  delay(5);
}
