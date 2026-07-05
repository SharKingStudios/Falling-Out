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
#define QMC5883_ALT_ADDR 0x2C
#define HMC5883L_ADDR 0x1E
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

const int IMU_ACCEL_X_SIGN = -1;
const int IMU_ACCEL_Y_SIGN = -1;
const int IMU_ACCEL_Z_SIGN = 1;
const int IMU_GYRO_Z_SIGN = -1;
const float GYRO_Z_DEADBAND_DPS = 1.8f;
const float COMPASS_CORRECTION_ALPHA = 0.0015f;
const float COMPASS_FUSION_MAX_ERR_DEG = 30.0f;
const float COMPASS_FUSION_MAX_GYRO_DPS = 22.0f;
const float COMPASS_MAX_CORRECTION_DEG = 0.18f;
const float COMPASS_MIN_FIELD_XY = 80.0f;
const float COMPASS_MAX_FIELD_XY = 18000.0f;
const float MAG_MOUNT_YAW_DEG = 180.0f;
const int MAG_HEADING_SIGN = -1;

const float GESTURE_START_G = 0.34f;
const float GESTURE_END_G = 0.14f;
const uint32_t GESTURE_MIN_MS = 80;
const uint32_t GESTURE_MAX_MS = 620;
const uint32_t GESTURE_STILL_MS = 70;
const int BEAM_DOWN_SIGN = 1;   // Current build: physical down reports positive linearZ.
const int BUBBLE_UP_SIGN = -1;  // Current build: physical up reports negative linearZ.
const float BEAM_DOWN_ACCEL_G = 0.46f;
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
bool compassIsQmc = true;
bool compassIsAltQmc = false;
bool headingInitialized = false;
uint8_t compassAddr = QMC5883L_ADDR;
uint8_t compassDataReg = 0x00;
const char *compassModeName = "none";
float headingDeg = 0.0f;
float headingOffsetDeg = 0.0f;
float rawCompassHeadingDeg = 0.0f;
float compassHeadingDeg = 0.0f;
float compassErrDeg = 0.0f;
float compassCorrectionDeg = 0.0f;
float compassFieldXY = 0.0f;
bool compassTrusted = false;
bool magCalReady = false;
float magCalOffsetX = 0.0f;
float magCalOffsetY = 0.0f;
float magCalScaleX = 1.0f;
float magCalScaleY = 1.0f;
float gyroZBias = 0.0f;
float gyroZDps = 0.0f;
uint32_t lastMpuUs = 0;

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
float gesturePeakBeam = 0.0f;
float gesturePeakBubble = 0.0f;
float gesturePeakMag = 0.0f;

bool recenterLastRaw = HIGH;
bool recenterPressed = false;
uint32_t recenterChangedMs = 0;
uint32_t fxUntilMs = 0;
uint8_t lastAction = ACTION_NONE;
bool magDebug = false;
bool aimDebug = false;
uint32_t lastMagDebugMs = 0;
uint32_t lastAimDebugMs = 0;
String serialLine = "";

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

void printHex2(uint8_t value) {
  if (value < 16) Serial.print("0");
  Serial.print(value, HEX);
}

int16_t be16(uint8_t hi, uint8_t lo);
int16_t le16(uint8_t lo, uint8_t hi);
void calibrateHeading();

bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void scanI2c() {
  Serial.print("I2C_SCAN,pins=sda");
  Serial.print(I2C_SDA_PIN);
  Serial.print("_scl");
  Serial.print(I2C_SCL_PIN);
  Serial.print(",addr=");
  bool any = false;
  for (uint8_t addr = 1; addr < 127; addr++) {
    if (i2cPresent(addr)) {
      if (any) Serial.print("|");
      Serial.print("0x");
      if (addr < 16) Serial.print("0");
      Serial.print(addr, HEX);
      any = true;
    }
  }
  if (!any) Serial.print("none");
  Serial.println();
}

void printCompassProbe(uint8_t addr) {
  uint8_t buf[12] = {};
  Serial.print("COMPASS_PROBE,addr=0x");
  printHex2(addr);
  Serial.print(",reg00=");
  if (readRegs(addr, 0x00, buf, sizeof(buf))) {
    for (uint8_t i = 0; i < sizeof(buf); i++) {
      if (i) Serial.print(" ");
      printHex2(buf[i]);
    }
  } else {
    Serial.print("READ_FAIL");
  }
  Serial.println();
}

uint8_t parseByteToken(String text) {
  text.trim();
  text.toUpperCase();
  int base = 10;
  if (text.startsWith("0X")) {
    base = 0;
  } else {
    for (uint8_t i = 0; i < text.length(); i++) {
      char c = text.charAt(i);
      if (c >= 'A' && c <= 'F') {
        base = 16;
        break;
      }
    }
  }
  return (uint8_t)strtoul(text.c_str(), nullptr, base);
}

String csvPart(String line, uint8_t index) {
  int start = 0;
  for (uint8_t i = 0; i < index; i++) {
    start = line.indexOf(',', start);
    if (start < 0) return "";
    start++;
  }
  int end = line.indexOf(',', start);
  if (end < 0) end = line.length();
  String part = line.substring(start, end);
  part.trim();
  return part;
}

void printRegisterDump(uint8_t addr, uint8_t start, uint8_t len) {
  uint8_t buf[32] = {};
  if (len > sizeof(buf)) len = sizeof(buf);
  Serial.print("DUMP,addr=0x");
  printHex2(addr);
  Serial.print(",start=0x");
  printHex2(start);
  Serial.print(",data=");
  if (readRegs(addr, start, buf, len)) {
    for (uint8_t i = 0; i < len; i++) {
      if (i) Serial.print(" ");
      printHex2(buf[i]);
    }
  } else {
    Serial.print("READ_FAIL");
  }
  Serial.println();
}

bool configureCompassHmc(uint8_t addr, const char *name) {
  compassAddr = addr;
  compassIsQmc = false;
  compassIsAltQmc = false;
  compassDataReg = 0x03;
  compassModeName = name;
  writeReg(compassAddr, 0x00, 0x70);
  writeReg(compassAddr, 0x01, 0x20);
  writeReg(compassAddr, 0x02, 0x00);
  delay(12);
  return true;
}

bool configureCompassQmc(uint8_t addr, const char *name) {
  compassAddr = addr;
  compassIsQmc = true;
  compassIsAltQmc = false;
  compassDataReg = 0x00;
  compassModeName = name;
  writeReg(compassAddr, 0x0B, 0x01);
  writeReg(compassAddr, 0x09, 0x1D);
  delay(12);
  return true;
}

bool configureCompassAlt(uint8_t addr, const char *name) {
  compassAddr = addr;
  compassIsQmc = true;
  compassIsAltQmc = true;
  compassDataReg = 0x01;
  compassModeName = name;
  writeReg(compassAddr, 0x0B, 0x01);
  writeReg(compassAddr, 0x0A, 0x1D);
  delay(12);
  return true;
}

bool readCompassRaw(int16_t &mx, int16_t &my, int16_t &mz, uint8_t *raw = nullptr) {
  uint8_t buf[6] = {};
  if (!readRegs(compassAddr, compassDataReg, buf, 6)) return false;
  if (raw != nullptr) {
    for (uint8_t i = 0; i < 6; i++) raw[i] = buf[i];
  }
  if (compassIsQmc) {
    mx = le16(buf[0], buf[1]);
    my = le16(buf[2], buf[3]);
    mz = le16(buf[4], buf[5]);
  } else {
    mx = be16(buf[0], buf[1]);
    mz = be16(buf[2], buf[3]);
    my = be16(buf[4], buf[5]);
  }
  return true;
}

float clampFloat(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

bool computeCompassSuggestion(int16_t mx, int16_t my, float &rawHeading, float &suggestHeading, float &fieldXY) {
  float fx = (float)mx;
  float fy = (float)my;
  if (magCalReady) {
    fx = (fx - magCalOffsetX) * magCalScaleX;
    fy = (fy - magCalOffsetY) * magCalScaleY;
  }
  fieldXY = sqrtf(fx * fx + fy * fy);
  if (fieldXY < 1.0f) return false;
  rawHeading = normalizeDeg(atan2f(fy, fx) * 180.0f / PI + MAG_MOUNT_YAW_DEG);
  suggestHeading = normalizeDeg((rawHeading - headingOffsetDeg) * MAG_HEADING_SIGN);
  return true;
}

bool compassCorrectionAllowed(float errDeg, float fieldXY) {
  if (fieldXY < COMPASS_MIN_FIELD_XY || fieldXY > COMPASS_MAX_FIELD_XY) return false;
  if (!mpuReady) return true;
  if (!magCalReady) return false;
  if (fabsf(gyroZDps) > COMPASS_FUSION_MAX_GYRO_DPS) return false;
  if (fabsf(errDeg) > COMPASS_FUSION_MAX_ERR_DEG) return false;
  return true;
}

bool refreshCompassSuggestionNow() {
  if (!compassReady) return false;
  int16_t mx = 0, my = 0, mz = 0;
  float suggested = compassHeadingDeg;
  if (!readCompassRaw(mx, my, mz)) return false;
  if (!computeCompassSuggestion(mx, my, rawCompassHeadingDeg, suggested, compassFieldXY)) return false;
  compassHeadingDeg = suggested;
  compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
  compassTrusted = compassCorrectionAllowed(compassErrDeg, compassFieldXY);
  return true;
}

void printAimSample() {
  refreshCompassSuggestionNow();
  Serial.print("AIM,");
  Serial.print(PLAYER_ID);
  Serial.print(",heading=");
  Serial.print(headingDeg, 1);
  Serial.print(",suggest=");
  Serial.print(compassHeadingDeg, 1);
  Serial.print(",err=");
  Serial.print(compassErrDeg, 1);
  Serial.print(",corr=");
  Serial.print(compassCorrectionDeg, 3);
  Serial.print(",trusted=");
  Serial.print(compassTrusted ? 1 : 0);
  Serial.print(",magCal=");
  Serial.print(magCalReady ? 1 : 0);
  Serial.print(",field=");
  Serial.print(compassFieldXY, 0);
  Serial.print(",raw=");
  Serial.print(rawCompassHeadingDeg, 1);
  Serial.print(",offset=");
  Serial.print(headingOffsetDeg, 1);
  Serial.print(",magSign=");
  Serial.print(MAG_HEADING_SIGN);
  Serial.print(",gyroZ=");
  Serial.println(gyroZDps, 1);
}

void printMagSample() {
  int16_t mx = 0, my = 0, mz = 0;
  uint8_t raw[6] = {};
  Serial.print("MAG,addr=0x");
  printHex2(compassAddr);
  Serial.print(",mode=");
  Serial.print(compassModeName);
  Serial.print(",dataReg=0x");
  printHex2(compassDataReg);
  Serial.print(",");
  if (readCompassRaw(mx, my, mz, raw)) {
    float suggested = compassHeadingDeg;
    if (computeCompassSuggestion(mx, my, rawCompassHeadingDeg, suggested, compassFieldXY)) {
      compassHeadingDeg = suggested;
      compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
      compassTrusted = compassCorrectionAllowed(compassErrDeg, compassFieldXY);
    }
    Serial.print("raw=");
    for (uint8_t i = 0; i < 6; i++) {
      if (i) Serial.print(" ");
      printHex2(raw[i]);
    }
    Serial.print(",xyz=");
    Serial.print(mx);
    Serial.print(",");
    Serial.print(my);
    Serial.print(",");
    Serial.print(mz);
    Serial.print(",rawCompass=");
    Serial.print(rawCompassHeadingDeg, 1);
    Serial.print(",compass=");
    Serial.print(compassHeadingDeg, 1);
    Serial.print(",suggest=");
    Serial.print(compassHeadingDeg, 1);
    Serial.print(",err=");
    Serial.print(compassErrDeg, 1);
    Serial.print(",corr=");
    Serial.print(compassCorrectionDeg, 3);
    Serial.print(",trusted=");
    Serial.print(compassTrusted ? 1 : 0);
    Serial.print(",field=");
    Serial.print(compassFieldXY, 0);
    Serial.print(",magCal=");
    Serial.print(magCalReady ? 1 : 0);
    Serial.print(",cal=");
    Serial.print(magCalOffsetX, 0);
    Serial.print(",");
    Serial.print(magCalOffsetY, 0);
    Serial.print(",");
    Serial.print(magCalScaleX, 3);
    Serial.print(",");
    Serial.print(magCalScaleY, 3);
    Serial.print(",heading=");
    Serial.print(headingDeg, 1);
    Serial.print(",offset=");
    Serial.print(headingOffsetDeg, 1);
    Serial.print(",mount=");
    Serial.print(MAG_MOUNT_YAW_DEG, 0);
    Serial.print(",magSign=");
    Serial.print(MAG_HEADING_SIGN);
    Serial.print(",gyroZ=");
    Serial.print(gyroZDps, 1);
  } else {
    Serial.print("READ_FAIL");
  }
  Serial.println();
}

void calibrateMagnetometer(uint32_t durationMs) {
  if (!compassReady) {
    Serial.println("MAG_CAL,ERR,no_compass");
    return;
  }
  if (durationMs < 2500) durationMs = 2500;
  if (durationMs > 20000) durationMs = 20000;

  int16_t mx = 0, my = 0, mz = 0;
  if (!readCompassRaw(mx, my, mz)) {
    Serial.println("MAG_CAL,ERR,read_fail");
    return;
  }

  int16_t minX = mx;
  int16_t maxX = mx;
  int16_t minY = my;
  int16_t maxY = my;
  uint32_t samples = 0;
  uint32_t started = millis();
  uint32_t nextPrint = started;

  Serial.print("MAG_CAL,START,ms=");
  Serial.println(durationMs);
  while (millis() - started < durationMs) {
    if (readCompassRaw(mx, my, mz)) {
      if (mx < minX) minX = mx;
      if (mx > maxX) maxX = mx;
      if (my < minY) minY = my;
      if (my > maxY) maxY = my;
      samples++;
    }
    uint32_t now = millis();
    if (now >= nextPrint) {
      nextPrint = now + 500;
      Serial.print("MAG_CAL,SAMPLE,count=");
      Serial.print(samples);
      Serial.print(",x=");
      Serial.print(minX);
      Serial.print("..");
      Serial.print(maxX);
      Serial.print(",y=");
      Serial.print(minY);
      Serial.print("..");
      Serial.println(maxY);
    }
    delay(20);
  }

  float xRadius = ((float)maxX - (float)minX) * 0.5f;
  float yRadius = ((float)maxY - (float)minY) * 0.5f;
  if (samples < 40 || xRadius < 30.0f || yRadius < 30.0f) {
    magCalReady = false;
    Serial.print("MAG_CAL,ERR,not_enough_motion,samples=");
    Serial.print(samples);
    Serial.print(",xRadius=");
    Serial.print(xRadius, 1);
    Serial.print(",yRadius=");
    Serial.println(yRadius, 1);
    return;
  }

  magCalOffsetX = ((float)minX + (float)maxX) * 0.5f;
  magCalOffsetY = ((float)minY + (float)maxY) * 0.5f;
  float avgRadius = (xRadius + yRadius) * 0.5f;
  magCalScaleX = avgRadius / xRadius;
  magCalScaleY = avgRadius / yRadius;
  magCalReady = true;
  headingInitialized = false;
  compassTrusted = false;
  compassCorrectionDeg = 0.0f;

  Serial.print("MAG_CAL,OK,samples=");
  Serial.print(samples);
  Serial.print(",offset=");
  Serial.print(magCalOffsetX, 1);
  Serial.print(",");
  Serial.print(magCalOffsetY, 1);
  Serial.print(",scale=");
  Serial.print(magCalScaleX, 4);
  Serial.print(",");
  Serial.print(magCalScaleY, 4);
  Serial.print(",x=");
  Serial.print(minX);
  Serial.print("..");
  Serial.print(maxX);
  Serial.print(",y=");
  Serial.print(minY);
  Serial.print("..");
  Serial.println(maxY);
}

void setCompassMode(String mode) {
  mode.trim();
  mode.toUpperCase();
  if (mode == "HMC") {
    configureCompassHmc(compassAddr, compassAddr == QMC5883_ALT_ADDR ? "HMC_ALT_0x2C" : "HMC_MANUAL");
  } else if (mode == "QMC") {
    configureCompassQmc(compassAddr, compassAddr == QMC5883_ALT_ADDR ? "QMC_0x2C" : "QMC_MANUAL");
  } else if (mode == "ALT") {
    configureCompassAlt(compassAddr, "ALT_DATA_0x01");
  } else {
    Serial.println("MODE_ERR,use MODE,HMC or MODE,QMC or MODE,ALT");
    return;
  }
  compassReady = true;
  headingInitialized = false;
  Serial.print("MODE_OK,");
  Serial.println(compassModeName);
  printCompassProbe(compassAddr);
  printMagSample();
}

void handleSerialCommand(String line) {
  line.trim();
  if (!line.length()) return;
  String upper = line;
  upper.toUpperCase();

  if (upper == "SCAN") {
    scanI2c();
  } else if (upper == "MAG") {
    printMagSample();
  } else if (upper == "AIM") {
    printAimSample();
  } else if (upper == "CAL") {
    calibrateHeading();
    printMagSample();
    printAimSample();
  } else if (upper == "MAGCALRESET") {
    magCalReady = false;
    magCalOffsetX = 0.0f;
    magCalOffsetY = 0.0f;
    magCalScaleX = 1.0f;
    magCalScaleY = 1.0f;
    headingInitialized = false;
    Serial.println("MAG_CAL,RESET");
  } else if (upper.startsWith("MAGCAL")) {
    uint32_t durationMs = (uint32_t)csvPart(upper, 1).toInt();
    if (durationMs == 0) durationMs = 8000;
    calibrateMagnetometer(durationMs);
    printMagSample();
    printAimSample();
  } else if (upper.startsWith("MAGDEBUG")) {
    String value = csvPart(upper, 1);
    magDebug = value == "" ? !magDebug : value.toInt() != 0;
    Serial.print("MAGDEBUG,");
    Serial.println(magDebug ? 1 : 0);
  } else if (upper.startsWith("AIMDEBUG")) {
    String value = csvPart(upper, 1);
    aimDebug = value == "" ? !aimDebug : value.toInt() != 0;
    Serial.print("AIMDEBUG,");
    Serial.println(aimDebug ? 1 : 0);
  } else if (upper.startsWith("DUMP")) {
    uint8_t addr = parseByteToken(csvPart(upper, 1));
    uint8_t start = parseByteToken(csvPart(upper, 2));
    uint8_t len = parseByteToken(csvPart(upper, 3));
    if (len == 0) len = 16;
    printRegisterDump(addr, start, len);
  } else if (upper.startsWith("POKE")) {
    uint8_t addr = parseByteToken(csvPart(upper, 1));
    uint8_t reg = parseByteToken(csvPart(upper, 2));
    uint8_t value = parseByteToken(csvPart(upper, 3));
    writeReg(addr, reg, value);
    Serial.print("POKE_OK,addr=0x");
    printHex2(addr);
    Serial.print(",reg=0x");
    printHex2(reg);
    Serial.print(",value=0x");
    printHex2(value);
    Serial.println();
    printRegisterDump(addr, reg, 1);
  } else if (upper.startsWith("MODE")) {
    setCompassMode(csvPart(upper, 1));
  } else {
    Serial.println("CMD?,SCAN|MAG|AIM|CAL|MAGCAL,8000|MAGCALRESET|MAGDEBUG,1|AIMDEBUG,1|DUMP,addr,start,len|POKE,addr,reg,value|MODE,HMC|QMC|ALT");
  }
}

void readSerialCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleSerialCommand(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < 120) {
      serialLine += c;
    }
  }
}

int16_t be16(uint8_t hi, uint8_t lo) {
  return (int16_t)((hi << 8) | lo);
}

int16_t le16(uint8_t lo, uint8_t hi) {
  return (int16_t)((hi << 8) | lo);
}

void setupMpu() {
  if (!i2cPresent(MPU6050_ADDR)) {
    Serial.println("MPU6050=MISSING_ADDR_0x68");
    mpuReady = false;
    return;
  }
  writeReg(MPU6050_ADDR, 0x6B, 0x00);
  writeReg(MPU6050_ADDR, 0x1B, 0x00);
  writeReg(MPU6050_ADDR, 0x1C, 0x00);
  delay(80);
  uint8_t who = 0;
  mpuReady = readRegs(MPU6050_ADDR, 0x75, &who, 1);
  if (mpuReady) {
    int32_t gzSum = 0;
    int samples = 0;
    uint8_t buf[6];
    for (int i = 0; i < 90; i++) {
      if (readRegs(MPU6050_ADDR, 0x43, buf, 6)) {
        gzSum += be16(buf[4], buf[5]);
        samples++;
      }
      delay(3);
    }
    if (samples > 20) {
      gyroZBias = (float)gzSum / (float)samples;
    }
    lastMpuUs = micros();
  }
  Serial.print("MPU6050=");
  Serial.print(mpuReady ? "OK" : "MISSING");
  Serial.print(",gzBias=");
  Serial.println(gyroZBias, 2);
}

void setupCompass() {
  if (i2cPresent(QMC5883L_ADDR)) {
    configureCompassQmc(QMC5883L_ADDR, "QMC_0x0D");
  } else if (i2cPresent(QMC5883_ALT_ADDR)) {
    configureCompassAlt(QMC5883_ALT_ADDR, "ALT_0x2C");
  } else if (i2cPresent(HMC5883L_ADDR)) {
    configureCompassHmc(HMC5883L_ADDR, "HMC_0x1E");
  } else {
    Serial.println("COMPASS=MISSING_ADDR_0x0D_OR_0x2C_OR_0x1E");
    compassReady = false;
    return;
  }
  delay(20);
  uint8_t buf[6] = {};
  compassReady = readRegs(compassAddr, compassDataReg, buf, 6);
  Serial.print("COMPASS=");
  Serial.println(compassReady ? "OK" : "MISSING");
  printCompassProbe(compassAddr);
  Serial.print("COMPASS_ADDR=0x");
  printHex2(compassAddr);
  Serial.print(",");
  Serial.println(compassModeName);
}

void updateMpu() {
  if (!mpuReady) return;
  uint8_t buf[14];
  if (!readRegs(MPU6050_ADDR, 0x3B, buf, 14)) return;
  uint32_t nowUs = micros();
  float dt = (float)(nowUs - lastMpuUs) / 1000000.0f;
  lastMpuUs = nowUs;
  if (dt <= 0.0f || dt > 0.2f) dt = 0.005f;
  accelX = ((float)be16(buf[0], buf[1]) * IMU_ACCEL_X_SIGN) / 16384.0f;
  accelY = ((float)be16(buf[2], buf[3]) * IMU_ACCEL_Y_SIGN) / 16384.0f;
  accelZ = ((float)be16(buf[4], buf[5]) * IMU_ACCEL_Z_SIGN) / 16384.0f;
  int16_t gzRaw = be16(buf[12], buf[13]);
  gyroZDps = (((float)gzRaw - gyroZBias) * IMU_GYRO_Z_SIGN) / 131.0f;
  if (fabsf(gyroZDps) < GYRO_Z_DEADBAND_DPS) {
    gyroZBias = gyroZBias * 0.995f + (float)gzRaw * 0.005f;
    gyroZDps = 0.0f;
  }
  if (!headingInitialized && !compassReady) {
    headingInitialized = true;
  }
  if (headingInitialized) {
    headingDeg = normalizeDeg(headingDeg + gyroZDps * dt);
  }
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
  int16_t mx = 0, my = 0, mz = 0;
  if (!readCompassRaw(mx, my, mz)) return;
  float suggested = compassHeadingDeg;
  if (!computeCompassSuggestion(mx, my, rawCompassHeadingDeg, suggested, compassFieldXY)) return;
  compassHeadingDeg = suggested;
  compassCorrectionDeg = 0.0f;
  compassTrusted = false;
  if (!headingInitialized) {
    headingOffsetDeg = rawCompassHeadingDeg;
    compassHeadingDeg = 0.0f;
    compassErrDeg = 0.0f;
    headingDeg = 0.0f;
    headingInitialized = true;
    return;
  }
  compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
  compassTrusted = compassCorrectionAllowed(compassErrDeg, compassFieldXY);
  if (!compassTrusted) return;
  float alpha = mpuReady ? COMPASS_CORRECTION_ALPHA : 0.25f;
  compassCorrectionDeg = clampFloat(compassErrDeg * alpha, -COMPASS_MAX_CORRECTION_DEG, COMPASS_MAX_CORRECTION_DEG);
  headingDeg = normalizeDeg(headingDeg + compassCorrectionDeg);
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
  gesturePeakBeam = linearZ * BEAM_DOWN_SIGN;
  gesturePeakBubble = linearZ * BUBBLE_UP_SIGN;
  gesturePeakMag = linearMag;
}

void updateGesture(uint32_t now) {
  gesturePeakUp = max(gesturePeakUp, linearZ);
  gesturePeakDown = min(gesturePeakDown, linearZ);
  gesturePeakBeam = max(gesturePeakBeam, linearZ * BEAM_DOWN_SIGN);
  gesturePeakBubble = max(gesturePeakBubble, linearZ * BUBBLE_UP_SIGN);
  gesturePeakMag = max(gesturePeakMag, linearMag);
  if (linearMag >= GESTURE_END_G) {
    gestureLastMotionMs = now;
  }
}

void finishGesture(uint32_t now) {
  uint32_t duration = now - gestureStartMs;
  if (duration >= GESTURE_MIN_MS && duration <= GESTURE_MAX_MS && gesturePeakMag >= GESTURE_START_G) {
    if (gesturePeakBeam >= BEAM_DOWN_ACCEL_G && gesturePeakBeam > gesturePeakBubble * 0.85f) {
      triggerAction(ACTION_BEAM);
    } else if (gesturePeakBubble >= BUBBLE_UP_ACCEL_G) {
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
  if (compassReady) {
    int16_t mx = 0, my = 0, mz = 0;
    float suggested = compassHeadingDeg;
    if (readCompassRaw(mx, my, mz) && computeCompassSuggestion(mx, my, rawCompassHeadingDeg, suggested, compassFieldXY)) {
      compassHeadingDeg = suggested;
      compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
    }
  }
  if (compassReady) {
    headingOffsetDeg = rawCompassHeadingDeg;
  } else {
    headingOffsetDeg = normalizeDeg(headingOffsetDeg + headingDeg);
  }
  headingDeg = 0.0f;
  compassHeadingDeg = 0.0f;
  headingInitialized = true;
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
  display.print(" MAG ");
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
  pinMode(I2C_SDA_PIN, INPUT_PULLUP);
  pinMode(I2C_SCL_PIN, INPUT_PULLUP);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(100000);
  Serial.println();
  Serial.println("Soupocalypse player");
  Serial.print("PLAYER_ID=");
  Serial.println(PLAYER_ID);
  scanI2c();
  setupDisplayAndLeds();
  setupMpu();
  setupCompass();
  setupEspNow();
  fxUntilMs = millis() + 600;
}

void loop() {
  uint32_t now = millis();
  readSerialCommands();
  updateMpu();
  updateCompass();
  updateButton();
  detectGestures();
  if (magDebug && now - lastMagDebugMs >= 350) {
    lastMagDebugMs = now;
    printMagSample();
  }
  if (aimDebug && now - lastAimDebugMs >= 220) {
    lastAimDebugMs = now;
    printAimSample();
  }
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
