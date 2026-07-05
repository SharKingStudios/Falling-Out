/*
  Soupocalypse player node.

  Hardware:
    ESP32
    Default stack: MPU6050 on I2C SDA=21/SCL=22 plus QMC/HMC/QMC5883P magnetometer.
    BMX055 stack: BMX055 module on the same I2C pins; can be used as magnetometer-only
    or as the full accel/gyro/mag replacement by changing SENSOR_STACK below.
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
#include <Preferences.h>

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

#if __has_include(<Adafruit_QMC5883P.h>)
#include <Adafruit_QMC5883P.h>
#define HAS_ADAFRUIT_QMC5883P 1
#else
#define HAS_ADAFRUIT_QMC5883P 0
#endif

#define PLAYER_ID 101

#define SENSOR_STACK_MPU6050_LEGACY_MAG 0
#define SENSOR_STACK_MPU6050_BMX055_MAG 1
#define SENSOR_STACK_BMX055_FULL 2
#define SENSOR_STACK SENSOR_STACK_MPU6050_LEGACY_MAG //SENSOR_STACK_MPU6050_LEGACY_MAG or SENSOR_STACK_BMX055_FULL

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define MPU6050_ADDR 0x68
#define BMX055_ACC_ADDR 0x18
#define BMX055_ACC_ALT_ADDR 0x19
#define BMX055_GYRO_ADDR 0x68
#define BMX055_GYRO_ALT_ADDR 0x69
#define BMM150_ADDR 0x10
#define BMM150_ALT_ADDR_1 0x11
#define BMM150_ALT_ADDR_2 0x12
#define BMM150_ALT_ADDR_3 0x13
#define QMC5883L_ADDR 0x0D
#define QMC5883L_ALT_ADDR 0x0C
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
const uint8_t PACKET_TYPE_COMMAND = 31;
const uint8_t PACKET_TYPE_MAGCAL = 32;
const uint8_t ACTION_NONE = 0;
const uint8_t ACTION_BEAM = 1;
const uint8_t ACTION_BUBBLE = 2;
const uint8_t PLAYER_CMD_NONE = 0;
const uint8_t PLAYER_CMD_MAGCAL = 1;
const uint8_t PLAYER_CMD_MAGCALRESET = 2;
const uint8_t PLAYER_CMD_CAL = 3;
const uint8_t MAGCAL_STATE_STARTED = 1;
const uint8_t MAGCAL_STATE_RUNNING = 2;
const uint8_t MAGCAL_STATE_OK = 3;
const uint8_t MAGCAL_STATE_ERR = 4;
const uint8_t MAGCAL_STATE_RESET = 5;

const uint32_t STATUS_INTERVAL_MS = 55;
const uint32_t ACTION_LOCKOUT_MS = 420;
const uint32_t RECENTER_DEBOUNCE_MS = 50;

const int IMU_ACCEL_X_SIGN = -1;
const int IMU_ACCEL_Y_SIGN = -1;
const int IMU_ACCEL_Z_SIGN = 1;
const int IMU_GYRO_Z_SIGN = -1;
const float BMX055_ACCEL_LSB_PER_G = 4096.0f;       // BMX055/BMA280, +/-2g, 14-bit
const float BMX055_GYRO_LSB_PER_DPS = 131.2f;      // BMX055/BMG160, +/-250 dps
const float GYRO_Z_DEADBAND_DPS = 1.8f;
const float COMPASS_CORRECTION_ALPHA_PER_SEC = 2.40f;
const float COMPASS_FUSION_MAX_GYRO_DPS = 55.0f;
const float COMPASS_FUSION_MAX_LINEAR_G = 0.85f;
const float COMPASS_MAX_CORRECTION_DPS = 120.0f;
const float COMPASS_STALE_MS = 220.0f;
const float COMPASS_FIELD_RATIO_MIN = 0.35f;
const float COMPASS_FIELD_RATIO_MAX = 2.70f;
const float COMPASS_RAW_FIELD_MIN = 80.0f;
const float COMPASS_RAW_FIELD_MAX = 50000.0f;
const bool MAG_AXIS_SWAP_XY = false;
const int MAG_X_SIGN = 1;
const int MAG_Y_SIGN = 1;
const int MAG_Z_SIGN = 1;
const float MAG_MOUNT_YAW_DEG = 180.0f;
const int MAG_HEADING_SIGN = -1;
const uint32_t MAGCAL_DEFAULT_MS = 18000;
const uint32_t MAGCAL_MIN_MS = 5000;
const uint32_t MAGCAL_MAX_MS = 30000;
const uint32_t MAGCAL_MIN_GOOD_MS = 10000;
const float MAGCAL_REQUIRED_XY_RADIUS = 80.0f;
const float MAGCAL_REQUIRED_Z_RADIUS = 45.0f;
const uint16_t MAGCAL_REQUIRED_SAMPLES = 120;
const uint16_t MAG_CAL_MAGIC = 0x51C1;
const uint8_t MAG_CAL_VERSION = 2;

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

struct __attribute__((packed)) PlayerCommandPacket {
  uint16_t magic;
  uint8_t packetType;
  uint8_t targetId;
  uint8_t command;
  uint16_t sequence;
  uint32_t valueMs;
};

struct __attribute__((packed)) PlayerMagCalPacket {
  uint16_t magic;
  uint8_t packetType;
  uint8_t playerId;
  uint16_t sequence;
  uint8_t state;
  uint8_t progress;
  uint8_t quality;
  uint8_t flags;
  uint16_t samples;
  uint16_t elapsedMs10;
  uint16_t remainingMs10;
  uint16_t radiusX;
  uint16_t radiusY;
  uint16_t radiusZ;
  uint16_t avgRadius;
};

enum CompassKind : uint8_t {
  COMPASS_NONE = 0,
  COMPASS_HMC5883L,
  COMPASS_QMC5883L,
  COMPASS_QMC5883P_ADAFRUIT,
  COMPASS_QMC5883P_QST,
  COMPASS_QMC5883P_GRANDDYSER,
  COMPASS_BMM150
};

struct MagCalibrationBlob {
  uint16_t magic;
  uint8_t version;
  uint8_t kind;
  uint8_t addr;
  float offsetX;
  float offsetY;
  float offsetZ;
  float scaleX;
  float scaleY;
  float scaleZ;
  float avgRadius;
};

uint16_t packetSequence = 0;
uint32_t lastStatusMs = 0;
uint32_t lastActionMs = 0;
uint32_t lastOledMs = 0;

bool mpuReady = false;
bool compassReady = false;
bool headingInitialized = false;
uint8_t compassAddr = QMC5883L_ADDR;
CompassKind compassKind = COMPASS_NONE;
uint8_t compassDataReg = 0x00;
uint8_t compassStatusReg = 0x00;
bool compassHasDrdy = false;
const char *compassModeName = "none";
float headingDeg = 0.0f;
float headingOffsetDeg = 0.0f;
float rawCompassHeadingDeg = 0.0f;
float compassHeadingDeg = 0.0f;
float compassErrDeg = 0.0f;
float compassCorrectionDeg = 0.0f;
float compassFieldXY = 0.0f;
float compassRawField = 0.0f;
float compassCalField = 0.0f;
float compassFieldRatio = 0.0f;
bool compassTrusted = false;
const char *compassTrustWhy = "no_compass";
uint32_t lastCompassReadMs = 0;
uint32_t lastCompassFusionMs = 0;
uint8_t lastCompassStatus = 0;
int16_t lastRawX = 0;
int16_t lastRawY = 0;
int16_t lastRawZ = 0;
uint8_t bmxAccelAddr = BMX055_ACC_ADDR;
uint8_t bmxGyroAddr = BMX055_GYRO_ADDR;
bool magCalReady = false;
bool magCalActive = false;
float magCalOffsetX = 0.0f;
float magCalOffsetY = 0.0f;
float magCalOffsetZ = 0.0f;
float magCalScaleX = 1.0f;
float magCalScaleY = 1.0f;
float magCalScaleZ = 1.0f;
float magCalAvgRadius = 0.0f;
float magCalMinX = 0.0f;
float magCalMaxX = 0.0f;
float magCalMinY = 0.0f;
float magCalMaxY = 0.0f;
float magCalMinZ = 0.0f;
float magCalMaxZ = 0.0f;
uint32_t magCalStartedMs = 0;
uint32_t magCalDurationMs = 0;
uint32_t magCalSamples = 0;
uint32_t magCalLastSampleMs = 0;
uint32_t magCalLastPrintMs = 0;
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
volatile uint8_t pendingRemoteCommand = PLAYER_CMD_NONE;
volatile uint32_t pendingRemoteValueMs = 0;
volatile uint16_t pendingRemoteSeq = 0;
uint16_t lastRemoteSeqHandled = 0xFFFF;

Preferences magPrefs;

bool magCalLooksGood(bool allowPartial);

#if HAS_ADAFRUIT_QMC5883P
Adafruit_QMC5883P qmc5883p;
#endif

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

float clampFloat(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

const char *compassKindName(CompassKind kind) {
  switch (kind) {
    case COMPASS_HMC5883L: return "HMC5883L";
    case COMPASS_QMC5883L: return "QMC5883L";
    case COMPASS_QMC5883P_ADAFRUIT: return "QMC5883P_ADAFRUIT";
    case COMPASS_QMC5883P_QST: return "QMC5883P_QST";
    case COMPASS_QMC5883P_GRANDDYSER: return "QMC5883P_GRANDDYSER";
    case COMPASS_BMM150: return "BMM150";
    default: return "NONE";
  }
}

String magCalKey() {
  char key[12];
  snprintf(key, sizeof(key), "cal%u_%02X", (unsigned)compassKind, compassAddr);
  return String(key);
}

void clearMagCalibration(bool eraseStore) {
  magCalReady = false;
  magCalActive = false;
  magCalOffsetX = 0.0f;
  magCalOffsetY = 0.0f;
  magCalOffsetZ = 0.0f;
  magCalScaleX = 1.0f;
  magCalScaleY = 1.0f;
  magCalScaleZ = 1.0f;
  magCalAvgRadius = 0.0f;
  if (eraseStore && compassKind != COMPASS_NONE) {
    magPrefs.begin("soup_mag", false);
    magPrefs.remove(magCalKey().c_str());
    magPrefs.end();
  }
}

void saveMagCalibration() {
  if (!magCalReady || compassKind == COMPASS_NONE) return;
  MagCalibrationBlob blob = {};
  blob.magic = MAG_CAL_MAGIC;
  blob.version = MAG_CAL_VERSION;
  blob.kind = (uint8_t)compassKind;
  blob.addr = compassAddr;
  blob.offsetX = magCalOffsetX;
  blob.offsetY = magCalOffsetY;
  blob.offsetZ = magCalOffsetZ;
  blob.scaleX = magCalScaleX;
  blob.scaleY = magCalScaleY;
  blob.scaleZ = magCalScaleZ;
  blob.avgRadius = magCalAvgRadius;
  magPrefs.begin("soup_mag", false);
  size_t wrote = magPrefs.putBytes(magCalKey().c_str(), &blob, sizeof(blob));
  magPrefs.end();
  Serial.print("MAG_CAL,SAVED,key=");
  Serial.print(magCalKey());
  Serial.print(",bytes=");
  Serial.println(wrote);
}

bool loadMagCalibration() {
  clearMagCalibration(false);
  if (compassKind == COMPASS_NONE) return false;
  MagCalibrationBlob blob = {};
  magPrefs.begin("soup_mag", true);
  size_t got = magPrefs.getBytes(magCalKey().c_str(), &blob, sizeof(blob));
  magPrefs.end();
  if (got != sizeof(blob) || blob.magic != MAG_CAL_MAGIC || blob.version != MAG_CAL_VERSION ||
      blob.kind != (uint8_t)compassKind || blob.addr != compassAddr || blob.avgRadius <= 1.0f) {
    Serial.print("MAG_CAL,LOAD,miss,key=");
    Serial.println(magCalKey());
    return false;
  }
  magCalOffsetX = blob.offsetX;
  magCalOffsetY = blob.offsetY;
  magCalOffsetZ = blob.offsetZ;
  magCalScaleX = blob.scaleX;
  magCalScaleY = blob.scaleY;
  magCalScaleZ = blob.scaleZ;
  magCalAvgRadius = blob.avgRadius;
  magCalReady = true;
  Serial.print("MAG_CAL,LOAD,ok,key=");
  Serial.print(magCalKey());
  Serial.print(",offset=");
  Serial.print(magCalOffsetX, 1);
  Serial.print(",");
  Serial.print(magCalOffsetY, 1);
  Serial.print(",");
  Serial.print(magCalOffsetZ, 1);
  Serial.print(",scale=");
  Serial.print(magCalScaleX, 3);
  Serial.print(",");
  Serial.print(magCalScaleY, 3);
  Serial.print(",");
  Serial.print(magCalScaleZ, 3);
  Serial.print(",radius=");
  Serial.println(magCalAvgRadius, 1);
  return true;
}

void setCompassMeta(CompassKind kind, uint8_t addr, uint8_t dataReg, uint8_t statusReg, bool hasDrdy, const char *name) {
  compassKind = kind;
  compassAddr = addr;
  compassDataReg = dataReg;
  compassStatusReg = statusReg;
  compassHasDrdy = hasDrdy;
  compassModeName = name;
  compassReady = false;
  headingInitialized = false;
  compassTrusted = false;
  compassTrustWhy = "init";
  lastCompassReadMs = 0;
  lastCompassStatus = 0;
}

bool configureCompassHmc(uint8_t addr) {
  setCompassMeta(COMPASS_HMC5883L, addr, 0x03, 0x09, false, "HMC5883L");
  writeReg(addr, 0x00, 0x70);
  writeReg(addr, 0x01, 0x20);
  writeReg(addr, 0x02, 0x00);
  delay(12);
  return true;
}

bool configureCompassQmc5883l(uint8_t addr) {
  setCompassMeta(COMPASS_QMC5883L, addr, 0x00, 0x06, false, "QMC5883L");
  writeReg(addr, 0x0B, 0x01);
  writeReg(addr, 0x09, 0x1D);
  delay(12);
  return true;
}

bool configureCompassQmc5883pQst(uint8_t addr) {
  setCompassMeta(COMPASS_QMC5883P_QST, addr, 0x01, 0x09, true, "P_QST");
  writeReg(addr, 0x0B, 0x80);
  delay(40);
  writeReg(addr, 0x29, 0x06);
  writeReg(addr, 0x0B, 0x08);
  writeReg(addr, 0x0A, 0xCD);
  delay(20);
  return true;
}

bool configureCompassQmc5883pGranddyser(uint8_t addr) {
  setCompassMeta(COMPASS_QMC5883P_GRANDDYSER, addr, 0x01, 0x09, true, "P_GRANDDYSER");
  writeReg(addr, 0x0D, 0x40);
  delay(10);
  writeReg(addr, 0x29, 0x06);
  delay(10);
  writeReg(addr, 0x0A, 0xCF);
  delay(10);
  writeReg(addr, 0x0B, 0x00);
  delay(20);
  return true;
}

bool configureCompassQmc5883pAdafruit(uint8_t addr) {
#if HAS_ADAFRUIT_QMC5883P
  setCompassMeta(COMPASS_QMC5883P_ADAFRUIT, addr, 0x01, 0x09, true, "P_ADAFRUIT");
  if (!qmc5883p.begin(addr, &Wire)) return false;
  qmc5883p.softReset();
  delay(60);
  if (!qmc5883p.begin(addr, &Wire)) return false;
  qmc5883p.setRange(QMC5883P_RANGE_8G);
  qmc5883p.setSetResetMode(QMC5883P_SETRESET_ON);
  qmc5883p.setODR(QMC5883P_ODR_50HZ);
  qmc5883p.setOSR(QMC5883P_OSR_4);
  qmc5883p.setDSR(QMC5883P_DSR_2);
  qmc5883p.setMode(QMC5883P_MODE_CONTINUOUS);
  delay(40);
  return true;
#else
  (void)addr;
  return false;
#endif
}

bool configureCompassBmm150(uint8_t addr) {
  setCompassMeta(COMPASS_BMM150, addr, 0x42, 0x48, true, "BMM150");
  writeReg(addr, 0x4B, 0x01);
  delay(6);
  uint8_t id = 0;
  if (!readRegs(addr, 0x40, &id, 1) || id != 0x32) {
    Serial.print("BMM150_INIT_FAIL,addr=0x");
    printHex2(addr);
    Serial.print(",chip=0x");
    printHex2(id);
    Serial.println();
    return false;
  }
  writeReg(addr, 0x51, 0x17);  // nXY = 47 repetitions
  writeReg(addr, 0x52, 0x52);  // nZ = 83 repetitions
  writeReg(addr, 0x4C, 0x28);  // normal mode, 20 Hz ODR
  delay(60);
  return true;
}

bool compassDataReady() {
  if (!compassHasDrdy) return true;
  uint8_t status = 0;
  if (!readRegs(compassAddr, compassStatusReg, &status, 1)) return false;
  lastCompassStatus = status;
  return (status & 0x01) != 0;
}

bool readCompassRaw(int16_t &mx, int16_t &my, int16_t &mz, uint8_t *raw = nullptr) {
  uint8_t buf[8] = {};
  if (compassKind == COMPASS_NONE) {
    compassTrustWhy = "no_compass";
    return false;
  }
  if (compassHasDrdy && !compassDataReady()) {
    compassTrustWhy = "stale";
    return false;
  }
#if HAS_ADAFRUIT_QMC5883P
  if (compassKind == COMPASS_QMC5883P_ADAFRUIT) {
    if (raw != nullptr) readRegs(compassAddr, compassDataReg, raw, 6);
    if (!qmc5883p.getRawMagnetic(&mx, &my, &mz)) {
      compassTrustWhy = "read_fail";
      return false;
    }
  } else
#endif
  {
    uint8_t readLen = compassKind == COMPASS_BMM150 ? 8 : 6;
    if (!readRegs(compassAddr, compassDataReg, buf, readLen)) {
      compassTrustWhy = "read_fail";
      return false;
    }
    if (raw != nullptr) {
      for (uint8_t i = 0; i < 6; i++) raw[i] = buf[i];
    }
    if (compassKind == COMPASS_HMC5883L) {
      mx = be16(buf[0], buf[1]);
      mz = be16(buf[2], buf[3]);
      my = be16(buf[4], buf[5]);
    } else if (compassKind == COMPASS_BMM150) {
      int16_t x = (int16_t)(((int16_t)buf[1] << 5) | (buf[0] >> 3));
      int16_t y = (int16_t)(((int16_t)buf[3] << 5) | (buf[2] >> 3));
      int16_t z = (int16_t)(((int16_t)buf[5] << 7) | (buf[4] >> 1));
      if (x > 4095) x -= 8192;
      if (y > 4095) y -= 8192;
      if (z > 16383) z -= 32768;
      mx = x;
      my = y;
      mz = z;
    } else {
      mx = le16(buf[0], buf[1]);
      my = le16(buf[2], buf[3]);
      mz = le16(buf[4], buf[5]);
    }
  }
  lastRawX = mx;
  lastRawY = my;
  lastRawZ = mz;
  lastCompassReadMs = millis();
  return true;
}

bool invalidCompassSample(int16_t x, int16_t y, int16_t z) {
  if (x == 0 && y == 0 && z == 0) return true;
  if (x == -1 && y == -1 && z == -1) return true;
  if (x == 32767 && y == 32767 && z == 32767) return true;
  if (x == -32768 && y == -32768 && z == -32768) return true;
  return false;
}

bool validateCompassMode(const char *label) {
  int16_t firstX = 0, firstY = 0, firstZ = 0;
  int16_t mx = 0, my = 0, mz = 0;
  uint8_t raw[6] = {};
  bool haveFirst = false;
  bool changed = false;
  int samples = 0;
  int invalid = 0;
  uint32_t deadline = millis() + 650;
  while (millis() < deadline && samples < 18) {
    if (readCompassRaw(mx, my, mz, samples == 0 ? raw : nullptr)) {
      if (invalidCompassSample(mx, my, mz)) invalid++;
      if (!haveFirst) {
        firstX = mx;
        firstY = my;
        firstZ = mz;
        haveFirst = true;
      } else if (abs(mx - firstX) + abs(my - firstY) + abs(mz - firstZ) > 4) {
        changed = true;
      }
      samples++;
    }
    delay(28);
  }
  bool ok = samples >= 3 && invalid < samples && (changed || !compassHasDrdy || compassKind == COMPASS_BMM150);
  Serial.print("MAG_VALIDATE,mode=");
  Serial.print(label);
  Serial.print(",addr=0x");
  printHex2(compassAddr);
  Serial.print(",status=0x");
  printHex2(lastCompassStatus);
  Serial.print(",samples=");
  Serial.print(samples);
  Serial.print(",changed=");
  Serial.print(changed ? 1 : 0);
  Serial.print(",raw=");
  for (uint8_t i = 0; i < 6; i++) {
    if (i) Serial.print(" ");
    printHex2(raw[i]);
  }
  Serial.print(",xyz=");
  Serial.print(firstX);
  Serial.print(",");
  Serial.print(firstY);
  Serial.print(",");
  Serial.print(firstZ);
  Serial.print(",");
  Serial.println(ok ? "PASS" : "FAIL");
  return ok;
}

bool acceptCompassMode(const char *label) {
  if (!validateCompassMode(label)) return false;
  compassReady = true;
  loadMagCalibration();
  Serial.print("MAG_INIT_OK,mode=");
  Serial.print(compassModeName);
  Serial.print(",kind=");
  Serial.print(compassKindName(compassKind));
  Serial.print(",addr=0x");
  printHex2(compassAddr);
  Serial.print(",dataReg=0x");
  printHex2(compassDataReg);
  Serial.print(",statusReg=0x");
  printHex2(compassStatusReg);
  Serial.print(",drdy=");
  Serial.println(compassHasDrdy ? 1 : 0);
  return true;
}

void applyMagAxes(int16_t mx, int16_t my, int16_t mz, float &fx, float &fy, float &fz) {
  fx = (float)mx * MAG_X_SIGN;
  fy = (float)my * MAG_Y_SIGN;
  fz = (float)mz * MAG_Z_SIGN;
  if (MAG_AXIS_SWAP_XY) {
    float tmp = fx;
    fx = fy;
    fy = tmp;
  }
}

bool computeCompassSuggestion(int16_t mx, int16_t my, int16_t mz, float &rawHeading, float &suggestHeading) {
  float fx, fy, fz;
  applyMagAxes(mx, my, mz, fx, fy, fz);
  compassRawField = sqrtf(fx * fx + fy * fy + fz * fz);
  if (magCalReady) {
    fx = (fx - magCalOffsetX) * magCalScaleX;
    fy = (fy - magCalOffsetY) * magCalScaleY;
    fz = (fz - magCalOffsetZ) * magCalScaleZ;
  }
  compassCalField = sqrtf(fx * fx + fy * fy + fz * fz);
  compassFieldRatio = (magCalReady && magCalAvgRadius > 1.0f) ? compassCalField / magCalAvgRadius : 0.0f;

  float hx = fx;
  float hy = fy;
  float gzMag = sqrtf(gravityX * gravityX + gravityY * gravityY + gravityZ * gravityZ);
  if (mpuReady && gzMag > 0.2f) {
    float gx = gravityX / gzMag;
    float gy = gravityY / gzMag;
    float gz = gravityZ / gzMag;
    float dot = fx * gx + fy * gy + fz * gz;
    hx = fx - dot * gx;
    hy = fy - dot * gy;
  }
  compassFieldXY = sqrtf(hx * hx + hy * hy);
  if (compassFieldXY < 1.0f) {
    compassTrustWhy = "field";
    return false;
  }
  rawHeading = normalizeDeg(atan2f(hy, hx) * 180.0f / PI + MAG_MOUNT_YAW_DEG);
  suggestHeading = normalizeDeg((rawHeading - headingOffsetDeg) * MAG_HEADING_SIGN);
  return true;
}

bool compassCorrectionAllowed(float errDeg) {
  uint32_t age = millis() - lastCompassReadMs;
  if (!compassReady) {
    compassTrustWhy = "no_compass";
    return false;
  }
  if (age > COMPASS_STALE_MS) {
    compassTrustWhy = "stale";
    return false;
  }
  if (magCalActive) {
    compassTrustWhy = "magcal";
    return false;
  }
  if (!magCalReady) {
    compassTrustWhy = "need_magcal";
    return false;
  }
  if (compassFieldRatio < COMPASS_FIELD_RATIO_MIN || compassFieldRatio > COMPASS_FIELD_RATIO_MAX) {
    compassTrustWhy = "field";
    return false;
  }
  if (linearMag > COMPASS_FUSION_MAX_LINEAR_G) {
    compassTrustWhy = "moving";
    return false;
  }
  if (fabsf(gyroZDps) > COMPASS_FUSION_MAX_GYRO_DPS) {
    compassTrustWhy = "gyro";
    return false;
  }
  compassTrustWhy = "ok";
  return true;
}

bool refreshCompassSuggestionNow() {
  int16_t mx = 0, my = 0, mz = 0;
  float suggested = compassHeadingDeg;
  if (!readCompassRaw(mx, my, mz)) return false;
  if (!computeCompassSuggestion(mx, my, mz, rawCompassHeadingDeg, suggested)) return false;
  compassHeadingDeg = suggested;
  compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
  compassTrusted = compassCorrectionAllowed(compassErrDeg);
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
  Serial.print(",why=");
  Serial.print(compassTrustWhy);
  Serial.print(",magCal=");
  Serial.print(magCalReady ? 1 : 0);
  Serial.print(",field=");
  Serial.print(compassCalField, 0);
  Serial.print(",ratio=");
  Serial.print(compassFieldRatio, 2);
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
  Serial.print(",kind=");
  Serial.print(compassKindName(compassKind));
  Serial.print(",status=0x");
  printHex2(lastCompassStatus);
  Serial.print(",dataReg=0x");
  printHex2(compassDataReg);
  Serial.print(",");
  if (readCompassRaw(mx, my, mz, raw)) {
    float suggested = compassHeadingDeg;
    computeCompassSuggestion(mx, my, mz, rawCompassHeadingDeg, suggested);
    compassHeadingDeg = suggested;
    compassErrDeg = normalizeDeg(compassHeadingDeg - headingDeg);
    compassTrusted = compassCorrectionAllowed(compassErrDeg);
    float fx, fy, fz;
    applyMagAxes(mx, my, mz, fx, fy, fz);
    float cfx = magCalReady ? (fx - magCalOffsetX) * magCalScaleX : fx;
    float cfy = magCalReady ? (fy - magCalOffsetY) * magCalScaleY : fy;
    float cfz = magCalReady ? (fz - magCalOffsetZ) * magCalScaleZ : fz;
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
    Serial.print(",cxyz=");
    Serial.print(cfx, 0);
    Serial.print(",");
    Serial.print(cfy, 0);
    Serial.print(",");
    Serial.print(cfz, 0);
    Serial.print(",fieldRaw=");
    Serial.print(compassRawField, 0);
    Serial.print(",fieldCal=");
    Serial.print(compassCalField, 0);
    Serial.print(",ratio=");
    Serial.print(compassFieldRatio, 2);
    Serial.print(",rawCompass=");
    Serial.print(rawCompassHeadingDeg, 1);
    Serial.print(",suggest=");
    Serial.print(compassHeadingDeg, 1);
    Serial.print(",err=");
    Serial.print(compassErrDeg, 1);
    Serial.print(",trusted=");
    Serial.print(compassTrusted ? 1 : 0);
    Serial.print(",why=");
    Serial.print(compassTrustWhy);
    Serial.print(",magCal=");
    Serial.print(magCalReady ? 1 : 0);
    Serial.print(",cal=");
    Serial.print(magCalOffsetX, 0);
    Serial.print(",");
    Serial.print(magCalOffsetY, 0);
    Serial.print(",");
    Serial.print(magCalOffsetZ, 0);
    Serial.print(",");
    Serial.print(magCalScaleX, 3);
    Serial.print(",");
    Serial.print(magCalScaleY, 3);
    Serial.print(",");
    Serial.print(magCalScaleZ, 3);
    Serial.print(",radius=");
    Serial.print(magCalAvgRadius, 1);
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
    Serial.print("READ_FAIL,why=");
    Serial.print(compassTrustWhy);
  }
  Serial.println();
}

float magCalRadiusX() {
  return (magCalMaxX - magCalMinX) * 0.5f;
}

float magCalRadiusY() {
  return (magCalMaxY - magCalMinY) * 0.5f;
}

float magCalRadiusZ() {
  return (magCalMaxZ - magCalMinZ) * 0.5f;
}

uint16_t clampU16(float value) {
  if (value <= 0.0f) return 0;
  if (value >= 65535.0f) return 65535;
  return (uint16_t)roundf(value);
}

uint8_t clampPercent(float value) {
  if (value <= 0.0f) return 0;
  if (value >= 100.0f) return 100;
  return (uint8_t)roundf(value);
}

uint8_t magCalMotionQuality(bool requireZ) {
  float rx = magCalRadiusX();
  float ry = magCalRadiusY();
  float rz = magCalRadiusZ();
  float sampleQ = clampFloat((float)magCalSamples / (float)MAGCAL_REQUIRED_SAMPLES, 0.0f, 1.0f);
  float xQ = clampFloat(rx / MAGCAL_REQUIRED_XY_RADIUS, 0.0f, 1.0f);
  float yQ = clampFloat(ry / MAGCAL_REQUIRED_XY_RADIUS, 0.0f, 1.0f);
  float zQ = requireZ ? clampFloat(rz / MAGCAL_REQUIRED_Z_RADIUS, 0.0f, 1.0f) : 1.0f;
  return clampPercent(100.0f * min(min(sampleQ, xQ), min(yQ, zQ)));
}

uint8_t magCalProgressPercent() {
  if (magCalReady && !magCalActive) return 100;
  if (!magCalStartedMs || !magCalDurationMs) return 0;
  uint32_t elapsed = millis() - magCalStartedMs;
  float timeQ = clampFloat(100.0f * (float)elapsed / (float)magCalDurationMs, 0.0f, 98.0f);
  float strictQ = (float)magCalMotionQuality(true);
  float progress = max(timeQ * 0.65f, min(strictQ, 98.0f));
  return clampPercent(progress);
}

const char *magCalStateName(uint8_t state) {
  if (state == MAGCAL_STATE_STARTED) return "START";
  if (state == MAGCAL_STATE_RUNNING) return "RUNNING";
  if (state == MAGCAL_STATE_OK) return "OK";
  if (state == MAGCAL_STATE_ERR) return "ERR";
  if (state == MAGCAL_STATE_RESET) return "RESET";
  return "UNKNOWN";
}

void sendMagCalStatus(uint8_t state) {
  uint32_t now = millis();
  uint32_t elapsed = magCalStartedMs ? now - magCalStartedMs : 0;
  uint32_t remaining = 0;
  if (magCalActive && elapsed < magCalDurationMs) {
    remaining = magCalDurationMs - elapsed;
  }

  float rx = magCalRadiusX();
  float ry = magCalRadiusY();
  float rz = magCalRadiusZ();
  bool strictGood = magCalLooksGood(false);
  bool partialGood = magCalLooksGood(true);

  PlayerMagCalPacket packet = {};
  packet.magic = PACKET_MAGIC;
  packet.packetType = PACKET_TYPE_MAGCAL;
  packet.playerId = PLAYER_ID;
  packet.sequence = packetSequence++;
  packet.state = state;
  packet.progress = state == MAGCAL_STATE_OK ? 100 : magCalProgressPercent();
  packet.quality = magCalMotionQuality(true);
  packet.flags = (compassReady ? 0x01 : 0x00) | (magCalActive ? 0x02 : 0x00) |
                 (magCalReady ? 0x04 : 0x00) | (strictGood ? 0x08 : 0x00) |
                 (partialGood ? 0x10 : 0x00);
  packet.samples = (uint16_t)min(magCalSamples, (uint32_t)65535);
  packet.elapsedMs10 = (uint16_t)min(elapsed / 10, (uint32_t)65535);
  packet.remainingMs10 = (uint16_t)min(remaining / 10, (uint32_t)65535);
  packet.radiusX = clampU16(rx);
  packet.radiusY = clampU16(ry);
  packet.radiusZ = clampU16(rz);
  packet.avgRadius = clampU16(magCalAvgRadius);
  esp_now_send(broadcastMac, (uint8_t *)&packet, sizeof(packet));

  Serial.print("MAG_CAL_STATUS,");
  Serial.print(PLAYER_ID);
  Serial.print(",");
  Serial.print(magCalStateName(state));
  Serial.print(",progress=");
  Serial.print(packet.progress);
  Serial.print(",quality=");
  Serial.print(packet.quality);
  Serial.print(",samples=");
  Serial.print(packet.samples);
  Serial.print(",elapsedMs=");
  Serial.print(elapsed);
  Serial.print(",remainingMs=");
  Serial.print(remaining);
  Serial.print(",radius=");
  Serial.print(rx, 0);
  Serial.print(",");
  Serial.print(ry, 0);
  Serial.print(",");
  Serial.print(rz, 0);
  Serial.print(",flags=0x");
  printHex2(packet.flags);
  Serial.println();
}

bool magCalLooksGood(bool allowPartial) {
  float rx = magCalRadiusX();
  float ry = magCalRadiusY();
  float rz = magCalRadiusZ();
  if (magCalSamples < MAGCAL_REQUIRED_SAMPLES || rx < MAGCAL_REQUIRED_XY_RADIUS || ry < MAGCAL_REQUIRED_XY_RADIUS) return false;
  if (!allowPartial && rz < MAGCAL_REQUIRED_Z_RADIUS) return false;
  return true;
}

void finishMagCalibration(bool ok) {
  magCalActive = false;
  float rx = magCalRadiusX();
  float ry = magCalRadiusY();
  float rz = magCalRadiusZ();
  if (!ok || rx < 30.0f || ry < 30.0f) {
    clearMagCalibration(false);
    Serial.print("MAG_CAL,ERR,not_enough_motion,samples=");
    Serial.print(magCalSamples);
    Serial.print(",radius=");
    Serial.print(rx, 1);
    Serial.print(",");
    Serial.print(ry, 1);
    Serial.print(",");
    Serial.println(rz, 1);
    sendMagCalStatus(MAGCAL_STATE_ERR);
    return;
  }
  if (rz < 30.0f) rz = (rx + ry) * 0.5f;
  magCalOffsetX = (magCalMinX + magCalMaxX) * 0.5f;
  magCalOffsetY = (magCalMinY + magCalMaxY) * 0.5f;
  magCalOffsetZ = (magCalMinZ + magCalMaxZ) * 0.5f;
  magCalAvgRadius = (rx + ry + rz) / 3.0f;
  magCalScaleX = magCalAvgRadius / rx;
  magCalScaleY = magCalAvgRadius / ry;
  magCalScaleZ = magCalAvgRadius / rz;
  magCalReady = true;
  headingInitialized = false;
  compassTrusted = false;
  compassTrustWhy = "saved";
  compassCorrectionDeg = 0.0f;
  saveMagCalibration();
  Serial.print("MAG_CAL,OK,samples=");
  Serial.print(magCalSamples);
  Serial.print(",offset=");
  Serial.print(magCalOffsetX, 1);
  Serial.print(",");
  Serial.print(magCalOffsetY, 1);
  Serial.print(",");
  Serial.print(magCalOffsetZ, 1);
  Serial.print(",scale=");
  Serial.print(magCalScaleX, 4);
  Serial.print(",");
  Serial.print(magCalScaleY, 4);
  Serial.print(",");
  Serial.print(magCalScaleZ, 4);
  Serial.print(",radius=");
  Serial.print(rx, 1);
  Serial.print(",");
  Serial.print(ry, 1);
  Serial.print(",");
  Serial.println(rz, 1);
  sendMagCalStatus(MAGCAL_STATE_OK);
}

void startMagCalibration(uint32_t durationMs) {
  if (!compassReady) {
    Serial.println("MAG_CAL,ERR,no_compass");
    return;
  }
  durationMs = constrain(durationMs ? durationMs : MAGCAL_DEFAULT_MS, MAGCAL_MIN_MS, MAGCAL_MAX_MS);
  int16_t mx = 0, my = 0, mz = 0;
  if (!readCompassRaw(mx, my, mz)) {
    Serial.println("MAG_CAL,ERR,read_fail");
    return;
  }
  float fx, fy, fz;
  applyMagAxes(mx, my, mz, fx, fy, fz);
  magCalMinX = magCalMaxX = fx;
  magCalMinY = magCalMaxY = fy;
  magCalMinZ = magCalMaxZ = fz;
  magCalSamples = 0;
  magCalStartedMs = millis();
  magCalDurationMs = durationMs;
  magCalLastSampleMs = 0;
  magCalLastPrintMs = 0;
  magCalActive = true;
  magCalReady = false;
  compassTrustWhy = "magcal";
  Serial.print("MAG_CAL,START,ms=");
  Serial.print(durationMs);
  Serial.println(",motion=figure8_tumble_until_done");
  sendMagCalStatus(MAGCAL_STATE_STARTED);
}

void updateMagCalibration() {
  if (!magCalActive) return;
  uint32_t now = millis();
  if (now - magCalLastSampleMs >= 25) {
    magCalLastSampleMs = now;
    int16_t mx = 0, my = 0, mz = 0;
    if (readCompassRaw(mx, my, mz)) {
      float fx, fy, fz;
      applyMagAxes(mx, my, mz, fx, fy, fz);
      magCalMinX = min(magCalMinX, fx);
      magCalMaxX = max(magCalMaxX, fx);
      magCalMinY = min(magCalMinY, fy);
      magCalMaxY = max(magCalMaxY, fy);
      magCalMinZ = min(magCalMinZ, fz);
      magCalMaxZ = max(magCalMaxZ, fz);
      magCalSamples++;
    }
  }
  if (now - magCalLastPrintMs >= 900) {
    magCalLastPrintMs = now;
    Serial.print("MAG_CAL,SAMPLE,count=");
    Serial.print(magCalSamples);
    Serial.print(",x=");
    Serial.print(magCalMinX, 0);
    Serial.print("..");
    Serial.print(magCalMaxX, 0);
    Serial.print(",y=");
    Serial.print(magCalMinY, 0);
    Serial.print("..");
    Serial.print(magCalMaxY, 0);
    Serial.print(",z=");
    Serial.print(magCalMinZ, 0);
    Serial.print("..");
    Serial.print(magCalMaxZ, 0);
    Serial.print(",good=");
    Serial.println(magCalLooksGood(false) ? 1 : 0);
    sendMagCalStatus(MAGCAL_STATE_RUNNING);
  }
  bool early = now - magCalStartedMs > MAGCAL_MIN_GOOD_MS && magCalLooksGood(false);
  bool timedOut = now - magCalStartedMs >= magCalDurationMs;
  if (early || timedOut) {
    finishMagCalibration(magCalLooksGood(timedOut));
  }
}

void printProbe() {
  Serial.println("PROBE,begin");
  if (i2cPresent(BMM150_ADDR)) printRegisterDump(BMM150_ADDR, 0x40, 0x13);
  if (i2cPresent(BMM150_ALT_ADDR_1)) printRegisterDump(BMM150_ALT_ADDR_1, 0x40, 0x13);
  if (i2cPresent(BMM150_ALT_ADDR_2)) printRegisterDump(BMM150_ALT_ADDR_2, 0x40, 0x13);
  if (i2cPresent(BMM150_ALT_ADDR_3)) printRegisterDump(BMM150_ALT_ADDR_3, 0x40, 0x13);
  if (i2cPresent(QMC5883_ALT_ADDR)) {
    printCompassProbe(QMC5883_ALT_ADDR);
    printRegisterDump(QMC5883_ALT_ADDR, 0x00, 0x10);
    printRegisterDump(QMC5883_ALT_ADDR, 0x29, 1);
  }
  if (i2cPresent(QMC5883L_ADDR)) printRegisterDump(QMC5883L_ADDR, 0x00, 0x0E);
  if (i2cPresent(QMC5883L_ALT_ADDR)) printRegisterDump(QMC5883L_ALT_ADDR, 0x00, 0x0E);
  if (i2cPresent(HMC5883L_ADDR)) printRegisterDump(HMC5883L_ADDR, 0x00, 0x0D);
  Serial.println("PROBE,end");
}

bool initCompassAuto() {
  compassReady = false;
  clearMagCalibration(false);
#if SENSOR_STACK == SENSOR_STACK_MPU6050_BMX055_MAG || SENSOR_STACK == SENSOR_STACK_BMX055_FULL
  if (i2cPresent(BMM150_ADDR) && configureCompassBmm150(BMM150_ADDR) && acceptCompassMode("BMM150_0x10")) return true;
  if (i2cPresent(BMM150_ALT_ADDR_1) && configureCompassBmm150(BMM150_ALT_ADDR_1) && acceptCompassMode("BMM150_0x11")) return true;
  if (i2cPresent(BMM150_ALT_ADDR_2) && configureCompassBmm150(BMM150_ALT_ADDR_2) && acceptCompassMode("BMM150_0x12")) return true;
  if (i2cPresent(BMM150_ALT_ADDR_3) && configureCompassBmm150(BMM150_ALT_ADDR_3) && acceptCompassMode("BMM150_0x13")) return true;
#endif
#if SENSOR_STACK == SENSOR_STACK_MPU6050_LEGACY_MAG
  if (i2cPresent(QMC5883_ALT_ADDR)) {
    uint8_t id = 0;
    readRegs(QMC5883_ALT_ADDR, 0x00, &id, 1);
    Serial.print("MAG_INIT_PROBE,addr=0x2C,id=0x");
    printHex2(id);
    Serial.println();
    if (id == 0x80) {
      if (configureCompassQmc5883pAdafruit(QMC5883_ALT_ADDR) && acceptCompassMode("P_ADAFRUIT")) return true;
      if (configureCompassQmc5883pQst(QMC5883_ALT_ADDR) && acceptCompassMode("P_QST")) return true;
      if (configureCompassQmc5883pGranddyser(QMC5883_ALT_ADDR) && acceptCompassMode("P_GRANDDYSER")) return true;
    }
  }
  if (i2cPresent(QMC5883L_ADDR) && configureCompassQmc5883l(QMC5883L_ADDR) && acceptCompassMode("QMC5883L_0x0D")) return true;
  if (i2cPresent(QMC5883L_ALT_ADDR) && configureCompassQmc5883l(QMC5883L_ALT_ADDR) && acceptCompassMode("QMC5883L_0x0C")) return true;
  if (i2cPresent(HMC5883L_ADDR) && configureCompassHmc(HMC5883L_ADDR) && acceptCompassMode("HMC5883L")) return true;
#endif
  compassKind = COMPASS_NONE;
  compassReady = false;
  compassTrustWhy = "no_compass";
  Serial.println("COMPASS=MISSING_OR_INVALID");
  return false;
}

void setCompassMode(String mode) {
  mode.trim();
  mode.toUpperCase();
  bool ok = false;
  if (mode == "AUTO" || mode == "") {
    ok = initCompassAuto();
  } else if (mode == "HMC") {
    ok = configureCompassHmc(HMC5883L_ADDR) && acceptCompassMode("HMC");
  } else if (mode == "QMC") {
    uint8_t addr = i2cPresent(QMC5883L_ADDR) ? QMC5883L_ADDR : QMC5883L_ALT_ADDR;
    ok = configureCompassQmc5883l(addr) && acceptCompassMode("QMC");
  } else if (mode == "P_ADAFRUIT" || mode == "ALT") {
    ok = configureCompassQmc5883pAdafruit(QMC5883_ALT_ADDR) && acceptCompassMode("P_ADAFRUIT");
  } else if (mode == "P_QST") {
    ok = configureCompassQmc5883pQst(QMC5883_ALT_ADDR) && acceptCompassMode("P_QST");
  } else if (mode == "P_GRANDDYSER") {
    ok = configureCompassQmc5883pGranddyser(QMC5883_ALT_ADDR) && acceptCompassMode("P_GRANDDYSER");
  } else if (mode == "BMM" || mode == "BMM150" || mode == "BMX055") {
    uint8_t addr = i2cPresent(BMM150_ADDR) ? BMM150_ADDR :
                   i2cPresent(BMM150_ALT_ADDR_1) ? BMM150_ALT_ADDR_1 :
                   i2cPresent(BMM150_ALT_ADDR_2) ? BMM150_ALT_ADDR_2 : BMM150_ALT_ADDR_3;
    ok = configureCompassBmm150(addr) && acceptCompassMode("BMM150");
  } else {
    Serial.println("MAG_INIT_ERR,use MAGINIT,AUTO|HMC|QMC|P_ADAFRUIT|P_QST|P_GRANDDYSER|BMM150");
    return;
  }
  Serial.print("MAG_INIT_RESULT,");
  Serial.println(ok ? "OK" : "FAIL");
}

void handleSerialCommand(String line) {
  line.trim();
  if (!line.length()) return;
  String upper = line;
  upper.toUpperCase();

  if (upper == "SCAN") {
    scanI2c();
  } else if (upper == "PROBE") {
    printProbe();
  } else if (upper == "MAG") {
    printMagSample();
  } else if (upper == "AIM") {
    printAimSample();
  } else if (upper == "CAL") {
    calibrateHeading();
    printMagSample();
    printAimSample();
  } else if (upper == "MAGCALRESET") {
    clearMagCalibration(true);
    headingInitialized = false;
    Serial.println("MAG_CAL,RESET");
    sendMagCalStatus(MAGCAL_STATE_RESET);
  } else if (upper.startsWith("MAGCAL")) {
    uint32_t durationMs = (uint32_t)csvPart(upper, 1).toInt();
    startMagCalibration(durationMs);
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
  } else if (upper.startsWith("MAGINIT") || upper.startsWith("MODE")) {
    setCompassMode(csvPart(upper, 1));
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
  } else {
    Serial.println("CMD?,SCAN|PROBE|MAG|AIM|CAL|MAGCAL,18000|MAGCALRESET|MAGINIT,AUTO|MAGINIT,BMM150|MAGINIT,P_ADAFRUIT|MAGDEBUG,1|AIMDEBUG,1|DUMP,addr,start,len|POKE,addr,reg,value");
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

int16_t signExtend(uint16_t value, uint8_t bits) {
  uint16_t mask = 1 << (bits - 1);
  value &= (1 << bits) - 1;
  return (int16_t)((value ^ mask) - mask);
}

bool setupBmx055Imu() {
  bmxAccelAddr = i2cPresent(BMX055_ACC_ADDR) ? BMX055_ACC_ADDR : BMX055_ACC_ALT_ADDR;
  bmxGyroAddr = i2cPresent(BMX055_GYRO_ALT_ADDR) ? BMX055_GYRO_ALT_ADDR : BMX055_GYRO_ADDR;
  bool accelPresent = i2cPresent(bmxAccelAddr);
  bool gyroPresent = i2cPresent(bmxGyroAddr);
  if (!accelPresent || !gyroPresent) {
    Serial.print("BMX055_IMU=MISSING,acc=0x");
    printHex2(bmxAccelAddr);
    Serial.print(",gyro=0x");
    printHex2(bmxGyroAddr);
    Serial.println();
    mpuReady = false;
    return false;
  }

  writeReg(bmxAccelAddr, 0x0F, 0x03);  // +/-2g
  writeReg(bmxAccelAddr, 0x10, 0x0C);  // ~125Hz bandwidth
  writeReg(bmxGyroAddr, 0x0F, 0x03);   // +/-250 dps
  writeReg(bmxGyroAddr, 0x10, 0x07);   // filtered normal mode
  delay(80);

  int32_t gzSum = 0;
  int samples = 0;
  uint8_t buf[6];
  for (int i = 0; i < 90; i++) {
    if (readRegs(bmxGyroAddr, 0x02, buf, 6)) {
      gzSum += le16(buf[4], buf[5]);
      samples++;
    }
    delay(3);
  }
  if (samples > 20) {
    gyroZBias = (float)gzSum / (float)samples;
  }
  lastMpuUs = micros();
  mpuReady = true;
  Serial.print("BMX055_IMU=OK,acc=0x");
  printHex2(bmxAccelAddr);
  Serial.print(",gyro=0x");
  printHex2(bmxGyroAddr);
  Serial.print(",gzBias=");
  Serial.println(gyroZBias, 2);
  return true;
}

void setupMpu() {
#if SENSOR_STACK == SENSOR_STACK_BMX055_FULL
  setupBmx055Imu();
  return;
#endif
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
  if (mpuReady && who != 0x68 && who != 0x69) {
    Serial.print("MPU6050=WRONG_WHOAMI_0x");
    printHex2(who);
    Serial.println();
    mpuReady = false;
    return;
  }
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
  Serial.print("COMPASS=");
  Serial.println(initCompassAuto() ? "OK" : "GYRO_ONLY");
  printCompassProbe(compassAddr);
  Serial.print("COMPASS_ADDR=0x");
  printHex2(compassAddr);
  Serial.print(",");
  Serial.println(compassModeName);
}

void updateMpu() {
#if SENSOR_STACK == SENSOR_STACK_BMX055_FULL
  if (!mpuReady) return;
  uint8_t accBuf[6];
  uint8_t gyroBuf[6];
  if (!readRegs(bmxAccelAddr, 0x02, accBuf, 6)) return;
  if (!readRegs(bmxGyroAddr, 0x02, gyroBuf, 6)) return;
  uint32_t nowUs = micros();
  float dt = (float)(nowUs - lastMpuUs) / 1000000.0f;
  lastMpuUs = nowUs;
  if (dt <= 0.0f || dt > 0.2f) dt = 0.005f;

  int16_t axRaw = signExtend(((uint16_t)accBuf[1] << 8 | accBuf[0]) >> 2, 14);
  int16_t ayRaw = signExtend(((uint16_t)accBuf[3] << 8 | accBuf[2]) >> 2, 14);
  int16_t azRaw = signExtend(((uint16_t)accBuf[5] << 8 | accBuf[4]) >> 2, 14);
  accelX = ((float)axRaw * IMU_ACCEL_X_SIGN) / BMX055_ACCEL_LSB_PER_G;
  accelY = ((float)ayRaw * IMU_ACCEL_Y_SIGN) / BMX055_ACCEL_LSB_PER_G;
  accelZ = ((float)azRaw * IMU_ACCEL_Z_SIGN) / BMX055_ACCEL_LSB_PER_G;

  int16_t gzRaw = le16(gyroBuf[4], gyroBuf[5]);
  gyroZDps = (((float)gzRaw - gyroZBias) * IMU_GYRO_Z_SIGN) / BMX055_GYRO_LSB_PER_DPS;
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
  return;
#endif
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
  if (!computeCompassSuggestion(mx, my, mz, rawCompassHeadingDeg, suggested)) return;
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
  compassTrusted = compassCorrectionAllowed(compassErrDeg);
  if (!compassTrusted) return;
  uint32_t now = millis();
  float dt = lastCompassFusionMs ? (float)(now - lastCompassFusionMs) / 1000.0f : 0.02f;
  lastCompassFusionMs = now;
  dt = clampFloat(dt, 0.001f, 0.080f);
  float alpha = mpuReady ? clampFloat(COMPASS_CORRECTION_ALPHA_PER_SEC * dt, 0.0f, 0.28f) : 0.35f;
  float maxStep = COMPASS_MAX_CORRECTION_DPS * dt;
  compassCorrectionDeg = clampFloat(compassErrDeg * alpha, -maxStep, maxStep);
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
    if (readCompassRaw(mx, my, mz) && computeCompassSuggestion(mx, my, mz, rawCompassHeadingDeg, suggested)) {
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
  if (magCalActive) {
    display.print("MAG CAL ");
    display.print(magCalProgressPercent());
    display.print("% keep moving");
  } else if (magCalReady) {
    display.print("MAG SAVED r=");
    display.print(magCalAvgRadius, 0);
  } else {
    display.print("Swing: down beam/up bub");
  }
  display.display();
#endif
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void onEspNowCommand(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  (void)info;
  if (len != sizeof(PlayerCommandPacket)) return;
  PlayerCommandPacket packet;
  memcpy(&packet, data, sizeof(packet));
  if (packet.magic != PACKET_MAGIC || packet.packetType != PACKET_TYPE_COMMAND) return;
  if (packet.targetId != PLAYER_ID && packet.targetId != 0) return;
  pendingRemoteCommand = packet.command;
  pendingRemoteValueMs = packet.valueMs;
  pendingRemoteSeq = packet.sequence;
}
#else
void onEspNowCommand(const uint8_t *mac, const uint8_t *data, int len) {
  (void)mac;
  if (len != sizeof(PlayerCommandPacket)) return;
  PlayerCommandPacket packet;
  memcpy(&packet, data, sizeof(packet));
  if (packet.magic != PACKET_MAGIC || packet.packetType != PACKET_TYPE_COMMAND) return;
  if (packet.targetId != PLAYER_ID && packet.targetId != 0) return;
  pendingRemoteCommand = packet.command;
  pendingRemoteValueMs = packet.valueMs;
  pendingRemoteSeq = packet.sequence;
}
#endif

void handlePendingRemoteCommand() {
  uint8_t command = pendingRemoteCommand;
  uint16_t seq = pendingRemoteSeq;
  if (command == PLAYER_CMD_NONE || seq == lastRemoteSeqHandled) return;
  noInterrupts();
  pendingRemoteCommand = PLAYER_CMD_NONE;
  uint32_t valueMs = pendingRemoteValueMs;
  interrupts();
  lastRemoteSeqHandled = seq;
  Serial.print("REMOTE_CMD,");
  Serial.print(command);
  Serial.print(",seq=");
  Serial.print(seq);
  Serial.print(",valueMs=");
  Serial.println(valueMs);
  if (command == PLAYER_CMD_MAGCAL) {
    startMagCalibration(valueMs ? valueMs : MAGCAL_DEFAULT_MS);
  } else if (command == PLAYER_CMD_MAGCALRESET) {
    clearMagCalibration(true);
    Serial.println("MAG_CAL,RESET");
    sendMagCalStatus(MAGCAL_STATE_RESET);
  } else if (command == PLAYER_CMD_CAL) {
    calibrateHeading();
  }
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
  esp_now_register_recv_cb(onEspNowCommand);
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
  Serial.print("SENSOR_STACK=");
  Serial.println(SENSOR_STACK);
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
  handlePendingRemoteCommand();
  updateMpu();
  updateMagCalibration();
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
