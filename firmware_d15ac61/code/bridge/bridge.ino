/*
  Soupocalypse bridge.

  Responsibilities:
    - Read HLK-LD2450 radar targets over Serial2.
    - Receive player ESP-NOW packets and expose RSSI.
    - Print simple serial protocol to laptop:
        RADAR,slot,xCm,yCm,speed,resolution
        PLAYER,id,headingDeg,action,seq,rssi,uptimeMs
    - Drive simple field effects for the Last Bowl Reactor.

  Bridge wiring:
    LD2450 TX -> ESP32 RX2 GPIO16
    LD2450 RX -> ESP32 TX2 GPIO17
    Relay/light -> GPIO25
    Relay/fan -> GPIO26
    Optional WS2812 DIN -> GPIO27
*/

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

#if __has_include(<Adafruit_NeoPixel.h>)
#include <Adafruit_NeoPixel.h>
#define HAS_NEOPIXEL 1
#else
#define HAS_NEOPIXEL 0
#endif

#define WIFI_CHANNEL 6
#define RADAR_RX_PIN 16
#define RADAR_TX_PIN 17
#define RADAR_BAUD 256000

const uint8_t LIGHT_RELAY_PIN = 25;
const uint8_t FAN_RELAY_PIN = 26;
const uint8_t LED_STRIP_PIN = 27;
const uint8_t SPARE_FX_1_PIN = 18;
const uint8_t SPARE_FX_2_PIN = 19;
const bool RELAY_ACTIVE_LOW = false;

const uint16_t PACKET_MAGIC = 0x51A7;
const uint8_t PACKET_TYPE_PLAYER = 20;

#if HAS_NEOPIXEL
Adafruit_NeoPixel pixels(24, LED_STRIP_PIN, NEO_GRB + NEO_KHZ800);
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

uint8_t radarBuffer[96];
uint8_t radarLen = 0;

uint32_t lightOffAt = 0;
uint32_t fanOffAt = 0;
uint32_t spareOffAt = 0;
uint32_t pixelOffAt = 0;
uint32_t pixelAnimUntil = 0;
uint32_t lastPixelAnimMs = 0;
uint8_t pixelAnimKind = 0;

void writeRelay(uint8_t pin, bool on) {
  digitalWrite(pin, RELAY_ACTIVE_LOW ? !on : on);
}

void setLight(bool on, uint32_t durationMs = 0) {
  writeRelay(LIGHT_RELAY_PIN, on);
  lightOffAt = on && durationMs ? millis() + durationMs : 0;
}

void setFan(bool on, uint32_t durationMs = 0) {
  writeRelay(FAN_RELAY_PIN, on);
  fanOffAt = on && durationMs ? millis() + durationMs : 0;
}

void setSpare(bool on, uint32_t durationMs = 0) {
  digitalWrite(SPARE_FX_1_PIN, on ? HIGH : LOW);
  digitalWrite(SPARE_FX_2_PIN, on ? HIGH : LOW);
  spareOffAt = on && durationMs ? millis() + durationMs : 0;
}

void pixelsSolid(uint8_t r, uint8_t g, uint8_t b, uint32_t durationMs) {
#if HAS_NEOPIXEL
  for (uint16_t i = 0; i < pixels.numPixels(); i++) {
    pixels.setPixelColor(i, pixels.Color(r, g, b));
  }
  pixels.show();
  pixelOffAt = durationMs ? millis() + durationMs : 0;
#else
  (void)r; (void)g; (void)b; (void)durationMs;
#endif
}

void pixelsOff() {
#if HAS_NEOPIXEL
  pixels.clear();
  pixels.show();
#endif
  pixelOffAt = 0;
}

void startPixelAnim(uint8_t kind, uint32_t durationMs) {
  pixelAnimKind = kind;
  pixelAnimUntil = millis() + durationMs;
  lastPixelAnimMs = 0;
}

void handleFx(String name) {
  name.trim();
  name.toLowerCase();
  if (name == "beam_fire") {
    setLight(true, 80);
    pixelsSolid(255, 180, 80, 120);
  } else if (name == "beam_hit") {
    setLight(true, 180);
    setSpare(true, 180);
    pixelsSolid(255, 255, 255, 160);
  } else if (name == "bubble" || name == "bubble_block") {
    setLight(true, 120);
    pixelsSolid(40, 200, 255, 170);
  } else if (name == "ko") {
    setLight(true, 350);
    setFan(true, 900);
    startPixelAnim(1, 950);
  } else if (name == "match_win") {
    setLight(true, 1200);
    setFan(true, 1500);
    startPixelAnim(2, 2200);
  }
}

int splitCsv(String line, String parts[], int maxParts) {
  int count = 0;
  int start = 0;
  while (count < maxParts && start <= line.length()) {
    int comma = line.indexOf(',', start);
    if (comma < 0) {
      parts[count++] = line.substring(start);
      break;
    }
    parts[count++] = line.substring(start, comma);
    start = comma + 1;
  }
  return count;
}

void handleSerialLine(String line) {
  line.trim();
  if (!line.length()) return;
  String parts[8];
  int count = splitCsv(line, parts, 8);
  parts[0].toUpperCase();
  if (parts[0] == "FX" && count >= 2) {
    handleFx(parts[1]);
  } else if (parts[0] == "RELAY" && count >= 4) {
    String name = parts[1];
    name.toLowerCase();
    bool on = parts[2] == "on" || parts[2] == "1";
    uint32_t ms = (uint32_t)parts[3].toInt();
    if (name == "light") setLight(on, ms);
    if (name == "fan") setFan(on, ms);
  }
}

void readLaptopSerial() {
  static String line = "";
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleSerialLine(line);
      line = "";
    } else if (c != '\r' && line.length() < 160) {
      line += c;
    }
  }
}

uint16_t u16le(uint8_t lo, uint8_t hi) {
  return (uint16_t)((hi << 8) | lo);
}

int16_t signedAxis(uint8_t lo, uint8_t hi) {
  uint16_t mag = u16le(lo, hi & 0x7F);
  int16_t cm = (int16_t)(mag / 10);
  return (hi & 0x80) ? cm : -cm;
}

int16_t signedSpeed(uint8_t lo, uint8_t hi) {
  uint16_t mag = u16le(lo, hi & 0x7F);
  int16_t value = (int16_t)mag;
  return (hi & 0x80) ? value : -value;
}

void parseRadarFrame(uint8_t *buf, uint8_t len) {
  if (len < 30) return;
  if (buf[0] != 0xAA || buf[1] != 0xFF || buf[2] != 0x03 || buf[3] != 0x00) return;
  if (buf[len - 2] != 0x55 || buf[len - 1] != 0xCC) return;
  for (uint8_t target = 0; target < 3; target++) {
    uint8_t *raw = &buf[4 + target * 8];
    int16_t x = signedAxis(raw[0], raw[1]);
    int16_t y = signedAxis(raw[2], raw[3]);
    int16_t speed = signedSpeed(raw[4], raw[5]);
    uint16_t resolution = u16le(raw[6], raw[7]);
    Serial.print("RADAR,");
    Serial.print(target + 1);
    Serial.print(",");
    Serial.print(x);
    Serial.print(",");
    Serial.print(y);
    Serial.print(",");
    Serial.print(speed);
    Serial.print(",");
    Serial.println(resolution);
  }
}

void readRadar() {
  while (Serial2.available()) {
    uint8_t b = (uint8_t)Serial2.read();
    if (radarLen == 0 && b != 0xAA) continue;
    radarBuffer[radarLen++] = b;
    if (radarLen >= 2 && radarBuffer[radarLen - 2] == 0x55 && radarBuffer[radarLen - 1] == 0xCC) {
      parseRadarFrame(radarBuffer, radarLen);
      radarLen = 0;
    } else if (radarLen >= sizeof(radarBuffer)) {
      radarLen = 0;
    }
  }
}

void printPlayerPacket(const PlayerPacket &packet, int rssi) {
  Serial.print("PLAYER,");
  Serial.print(packet.playerId);
  Serial.print(",");
  Serial.print((float)packet.headingDeg10 / 10.0f, 1);
  Serial.print(",");
  Serial.print(packet.action);
  Serial.print(",");
  Serial.print(packet.sequence);
  Serial.print(",");
  Serial.print(rssi);
  Serial.print(",");
  Serial.println(packet.uptimeMs);
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void onDataRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  int rssi = -127;
  if (info != nullptr && info->rx_ctrl != nullptr) {
    rssi = info->rx_ctrl->rssi;
  }
  if (len != sizeof(PlayerPacket)) return;
  PlayerPacket packet;
  memcpy(&packet, data, sizeof(packet));
  if (packet.magic == PACKET_MAGIC && packet.packetType == PACKET_TYPE_PLAYER) {
    printPlayerPacket(packet, rssi);
  }
}
#else
void onDataRecv(const uint8_t *mac, const uint8_t *data, int len) {
  (void)mac;
  if (len != sizeof(PlayerPacket)) return;
  PlayerPacket packet;
  memcpy(&packet, data, sizeof(packet));
  if (packet.magic == PACKET_MAGIC && packet.packetType == PACKET_TYPE_PLAYER) {
    printPlayerPacket(packet, -127);
  }
}
#endif

void setupEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("ERR,ESP_NOW_INIT");
    delay(1000);
    ESP.restart();
  }
  esp_now_register_recv_cb(onDataRecv);
}

void setupFx() {
  pinMode(LIGHT_RELAY_PIN, OUTPUT);
  pinMode(FAN_RELAY_PIN, OUTPUT);
  pinMode(SPARE_FX_1_PIN, OUTPUT);
  pinMode(SPARE_FX_2_PIN, OUTPUT);
  setLight(false);
  setFan(false);
  setSpare(false);
#if HAS_NEOPIXEL
  pixels.begin();
  pixels.clear();
  pixels.show();
#endif
}

void updateFx() {
  uint32_t now = millis();
  if (lightOffAt && now >= lightOffAt) setLight(false);
  if (fanOffAt && now >= fanOffAt) setFan(false);
  if (spareOffAt && now >= spareOffAt) setSpare(false);
  if (pixelOffAt && now >= pixelOffAt) pixelsOff();
#if HAS_NEOPIXEL
  if (pixelAnimKind && now < pixelAnimUntil && now - lastPixelAnimMs >= 38) {
    lastPixelAnimMs = now;
    for (uint16_t i = 0; i < pixels.numPixels(); i++) {
      uint8_t wave = (uint8_t)((sin((float)(now / 70 + i) * 0.55f) + 1.0f) * 85.0f);
      if (pixelAnimKind == 1) {
        pixels.setPixelColor(i, pixels.Color(255, 120 + wave / 2, 12));
      } else {
        pixels.setPixelColor(i, pixels.Color(255, 80 + wave, 30 + wave / 3));
      }
    }
    pixels.show();
  } else if (pixelAnimKind && now >= pixelAnimUntil) {
    pixelAnimKind = 0;
    pixelsOff();
  }
#endif
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(RADAR_BAUD, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);
  setupFx();
  delay(250);
  Serial.println();
  Serial.print("BRIDGE_BOOT,reset_reason=");
  Serial.println((int)esp_reset_reason());
  Serial.println("Soupocalypse bridge ready");
  setupEspNow();
}

void loop() {
  readLaptopSerial();
  readRadar();
  updateFx();
  delay(2);
}
