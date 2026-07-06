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
#define RADAR_AUTO_BAUD 0

const uint32_t RADAR_BAUDS[] = {RADAR_BAUD, 115200, 230400, 9600};
const uint8_t RADAR_BAUD_COUNT = sizeof(RADAR_BAUDS) / sizeof(RADAR_BAUDS[0]);
const uint8_t RADAR_RX_PINS[] = {RADAR_RX_PIN, RADAR_TX_PIN};
const uint8_t RADAR_TX_PINS[] = {RADAR_TX_PIN, RADAR_RX_PIN};
const uint8_t RADAR_PIN_MODE_COUNT = sizeof(RADAR_RX_PINS) / sizeof(RADAR_RX_PINS[0]);
const uint32_t RADAR_STATUS_INTERVAL_MS = 500;
const uint32_t RADAR_AUTO_BAUD_INTERVAL_MS = 2600;

const uint8_t LIGHT_RELAY_PIN = 25;
const uint8_t FAN_RELAY_PIN = 26;
const uint8_t LED_STRIP_PIN = 27;
const uint8_t SPARE_FX_1_PIN = 18;
const uint8_t SPARE_FX_2_PIN = 19;
const bool RELAY_ACTIVE_LOW = false;

const uint16_t PACKET_MAGIC = 0x51A7;
const uint8_t PACKET_TYPE_PLAYER = 20;
const uint8_t PACKET_TYPE_COMMAND = 31;
const uint8_t PACKET_TYPE_MAGCAL = 32;
const uint8_t PLAYER_CMD_NONE = 0;
const uint8_t PLAYER_CMD_MAGCAL = 1;
const uint8_t PLAYER_CMD_MAGCALRESET = 2;
const uint8_t PLAYER_CMD_CAL = 3;
const uint8_t MAGCAL_STATE_STARTED = 1;
const uint8_t MAGCAL_STATE_RUNNING = 2;
const uint8_t MAGCAL_STATE_OK = 3;
const uint8_t MAGCAL_STATE_ERR = 4;
const uint8_t MAGCAL_STATE_RESET = 5;

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

uint8_t broadcastMac[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint16_t commandSequence = 0;
uint8_t radarBuffer[96];
uint8_t radarLen = 0;
uint8_t radarBaudIndex = 0;
uint8_t radarPinModeIndex = 0;
uint32_t radarCurrentBaud = RADAR_BAUD;
uint32_t radarBaudStartedAt = 0;
uint32_t radarRxBytes = 0;
uint32_t radarBytesSinceBaud = 0;
uint32_t radarValidFrames = 0;
uint32_t radarBadFrames = 0;
uint32_t radarDroppedBytes = 0;
uint32_t radarLastByteAt = 0;
uint32_t radarLastValidAt = 0;
uint32_t radarLastStatusAt = 0;
uint8_t radarRecentBytes[12];
uint8_t radarRecentIndex = 0;
uint8_t radarRecentCount = 0;

void beginRadar(uint32_t baud);

struct PendingPlayerRx {
  bool pending;
  PlayerPacket packet;
  int rssi;
};

struct PendingMagCalRx {
  bool pending;
  PlayerMagCalPacket packet;
  int rssi;
};

PendingPlayerRx pendingPlayers[2];
PendingMagCalRx pendingMagCals[2];
portMUX_TYPE espNowMux = portMUX_INITIALIZER_UNLOCKED;

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

uint8_t parsePlayerCommand(String command) {
  command.trim();
  command.toUpperCase();
  if (command == "MAGCAL") return PLAYER_CMD_MAGCAL;
  if (command == "MAGCALRESET") return PLAYER_CMD_MAGCALRESET;
  if (command == "CAL") return PLAYER_CMD_CAL;
  return PLAYER_CMD_NONE;
}

void sendPlayerCommand(uint8_t targetId, uint8_t command, uint32_t valueMs) {
  PlayerCommandPacket packet = {};
  packet.magic = PACKET_MAGIC;
  packet.packetType = PACKET_TYPE_COMMAND;
  packet.targetId = targetId;
  packet.command = command;
  packet.sequence = commandSequence++;
  packet.valueMs = valueMs;
  esp_err_t result = esp_now_send(broadcastMac, (uint8_t *)&packet, sizeof(packet));
  Serial.print(result == ESP_OK ? "PLAYERCMD_SENT," : "PLAYERCMD_ERR,");
  Serial.print(targetId);
  Serial.print(",");
  Serial.print(command);
  Serial.print(",");
  Serial.print(packet.sequence);
  Serial.print(",");
  Serial.println(valueMs);
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
  } else if (parts[0] == "PLAYERCMD" && count >= 3) {
    uint8_t targetId = (uint8_t)parts[1].toInt();
    uint8_t command = parsePlayerCommand(parts[2]);
    uint32_t valueMs = count >= 4 ? (uint32_t)parts[3].toInt() : 0;
    if (command == PLAYER_CMD_NONE) {
      Serial.println("PLAYERCMD_ERR,bad_command");
      return;
    }
    sendPlayerCommand(targetId, command, valueMs);
  } else if (parts[0] == "RADARBAUD" && count >= 2) {
    uint32_t baud = (uint32_t)parts[1].toInt();
    if (baud > 0) {
      for (uint8_t i = 0; i < RADAR_BAUD_COUNT; i++) {
        if (RADAR_BAUDS[i] == baud) radarBaudIndex = i;
      }
      beginRadar(baud);
    }
  } else if (parts[0] == "RADARPINS" && count >= 2) {
    parts[1].toUpperCase();
    radarPinModeIndex = parts[1] == "SWAP" || parts[1] == "SWAPPED" || parts[1] == "1" ? 1 : 0;
    beginRadar(radarCurrentBaud);
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

void printHexByte(uint8_t value) {
  if (value < 16) Serial.print("0");
  Serial.print(value, HEX);
}

void printRecentRadarBytes() {
  uint8_t count = radarRecentCount;
  uint8_t start = (radarRecentIndex + 12 - count) % 12;
  for (uint8_t i = 0; i < count; i++) {
    printHexByte(radarRecentBytes[(start + i) % 12]);
  }
}

void rememberRadarByte(uint8_t b) {
  radarRecentBytes[radarRecentIndex] = b;
  radarRecentIndex = (radarRecentIndex + 1) % 12;
  if (radarRecentCount < 12) radarRecentCount++;
}

void beginRadar(uint32_t baud) {
  Serial2.end();
  delay(20);
  radarCurrentBaud = baud;
  radarBaudStartedAt = millis();
  radarBytesSinceBaud = 0;
  radarLen = 0;
  radarRecentIndex = 0;
  radarRecentCount = 0;
  Serial2.setRxBufferSize(1024);
  Serial2.begin(radarCurrentBaud, SERIAL_8N1, RADAR_RX_PINS[radarPinModeIndex], RADAR_TX_PINS[radarPinModeIndex]);
  Serial.print("RADAR_BAUD,");
  Serial.print(radarCurrentBaud);
  Serial.print(",rx=");
  Serial.print(RADAR_RX_PINS[radarPinModeIndex]);
  Serial.print(",tx=");
  Serial.println(RADAR_TX_PINS[radarPinModeIndex]);
}

bool parseRadarFrame(uint8_t *buf, uint8_t len) {
  if (len < 30) return false;
  if (buf[0] != 0xAA || buf[1] != 0xFF || buf[2] != 0x03 || buf[3] != 0x00) return false;
  if (buf[len - 2] != 0x55 || buf[len - 1] != 0xCC) return false;
  radarValidFrames++;
  radarLastValidAt = millis();
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
  return true;
}

void resetRadarParser(uint8_t nextByte) {
  radarLen = 0;
  if (nextByte == 0xAA) {
    radarBuffer[radarLen++] = nextByte;
  }
}

void readRadar() {
  while (Serial2.available()) {
    uint8_t b = (uint8_t)Serial2.read();
    radarRxBytes++;
    radarBytesSinceBaud++;
    radarLastByteAt = millis();
    rememberRadarByte(b);
    if (radarLen == 0 && b != 0xAA) {
      radarDroppedBytes++;
      continue;
    }
    radarBuffer[radarLen++] = b;

    if (radarLen == 2 && radarBuffer[1] != 0xFF) {
      radarBadFrames++;
      resetRadarParser(b);
    } else if (radarLen == 4 && (radarBuffer[2] != 0x03 || radarBuffer[3] != 0x00)) {
      radarBadFrames++;
      resetRadarParser(b);
    } else if (radarLen >= 2 && radarBuffer[radarLen - 2] == 0x55 && radarBuffer[radarLen - 1] == 0xCC) {
      if (!parseRadarFrame(radarBuffer, radarLen)) {
        radarBadFrames++;
      }
      radarLen = 0;
    } else if (radarLen >= sizeof(radarBuffer)) {
      radarBadFrames++;
      radarLen = 0;
    }
  }
}

void maybeCycleRadarBaud() {
#if RADAR_AUTO_BAUD
  if (radarValidFrames > 0) return;
  uint32_t now = millis();
  if (now - radarBaudStartedAt < RADAR_AUTO_BAUD_INTERVAL_MS) return;
  radarBaudIndex = (radarBaudIndex + 1) % RADAR_BAUD_COUNT;
  if (radarBaudIndex == 0) {
    radarPinModeIndex = (radarPinModeIndex + 1) % RADAR_PIN_MODE_COUNT;
  }
  beginRadar(RADAR_BAUDS[radarBaudIndex]);
#endif
}

void printRadarStatus() {
  uint32_t now = millis();
  if (now - radarLastStatusAt < RADAR_STATUS_INTERVAL_MS) return;
  radarLastStatusAt = now;
  int32_t byteAge = radarLastByteAt ? (int32_t)(now - radarLastByteAt) : -1;
  int32_t validAge = radarLastValidAt ? (int32_t)(now - radarLastValidAt) : -1;
  Serial.print("RADAR_STATUS,");
  Serial.print(radarCurrentBaud);
  Serial.print(",");
  Serial.print(radarRxBytes);
  Serial.print(",");
  Serial.print(radarValidFrames);
  Serial.print(",");
  Serial.print(radarBadFrames);
  Serial.print(",");
  Serial.print(radarDroppedBytes);
  Serial.print(",");
  Serial.print(byteAge);
  Serial.print(",");
  Serial.print(validAge);
  Serial.print(",");
  Serial.print(radarLen);
  Serial.print(",");
  Serial.print(radarBytesSinceBaud);
  Serial.print(",");
  printRecentRadarBytes();
  Serial.print(",");
  Serial.print(RADAR_RX_PINS[radarPinModeIndex]);
  Serial.print(",");
  Serial.print(RADAR_TX_PINS[radarPinModeIndex]);
  Serial.println();
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

const char *magCalStateName(uint8_t state) {
  if (state == MAGCAL_STATE_STARTED) return "START";
  if (state == MAGCAL_STATE_RUNNING) return "RUNNING";
  if (state == MAGCAL_STATE_OK) return "OK";
  if (state == MAGCAL_STATE_ERR) return "ERR";
  if (state == MAGCAL_STATE_RESET) return "RESET";
  return "UNKNOWN";
}

void printMagCalPacket(const PlayerMagCalPacket &packet, int rssi) {
  Serial.print("MAGCAL,");
  Serial.print(packet.playerId);
  Serial.print(",");
  Serial.print(magCalStateName(packet.state));
  Serial.print(",");
  Serial.print((int)packet.progress);
  Serial.print(",");
  Serial.print((int)packet.quality);
  Serial.print(",");
  Serial.print(packet.samples);
  Serial.print(",");
  Serial.print((uint32_t)packet.elapsedMs10 * 10UL);
  Serial.print(",");
  Serial.print((uint32_t)packet.remainingMs10 * 10UL);
  Serial.print(",");
  Serial.print(packet.radiusX);
  Serial.print(",");
  Serial.print(packet.radiusY);
  Serial.print(",");
  Serial.print(packet.radiusZ);
  Serial.print(",");
  Serial.print(packet.avgRadius);
  Serial.print(",");
  Serial.print((int)packet.flags);
  Serial.print(",");
  Serial.println(rssi);
}

int playerQueueIndex(uint8_t playerId) {
  if (playerId == 101) return 0;
  if (playerId == 102) return 1;
  return -1;
}

void handleEspNowData(const uint8_t *data, int len, int rssi) {
  if (len < 3) return;
  uint16_t magic = 0;
  memcpy(&magic, data, sizeof(magic));
  if (magic != PACKET_MAGIC) return;
  uint8_t packetType = data[2];
  if (packetType == PACKET_TYPE_PLAYER && len == sizeof(PlayerPacket)) {
    PlayerPacket packet;
    memcpy(&packet, data, sizeof(packet));
    int index = playerQueueIndex(packet.playerId);
    if (index < 0) return;
    portENTER_CRITICAL(&espNowMux);
    pendingPlayers[index].packet = packet;
    pendingPlayers[index].rssi = rssi;
    pendingPlayers[index].pending = true;
    portEXIT_CRITICAL(&espNowMux);
  } else if (packetType == PACKET_TYPE_MAGCAL && len == sizeof(PlayerMagCalPacket)) {
    PlayerMagCalPacket packet;
    memcpy(&packet, data, sizeof(packet));
    int index = playerQueueIndex(packet.playerId);
    if (index < 0) return;
    portENTER_CRITICAL(&espNowMux);
    pendingMagCals[index].packet = packet;
    pendingMagCals[index].rssi = rssi;
    pendingMagCals[index].pending = true;
    portEXIT_CRITICAL(&espNowMux);
  }
}

void flushEspNowPackets() {
  for (uint8_t i = 0; i < 2; i++) {
    PendingPlayerRx playerCopy = {};
    PendingMagCalRx magCopy = {};
    portENTER_CRITICAL(&espNowMux);
    if (pendingPlayers[i].pending) {
      playerCopy = pendingPlayers[i];
      pendingPlayers[i].pending = false;
    }
    if (pendingMagCals[i].pending) {
      magCopy = pendingMagCals[i];
      pendingMagCals[i].pending = false;
    }
    portEXIT_CRITICAL(&espNowMux);

    if (playerCopy.pending) {
      printPlayerPacket(playerCopy.packet, playerCopy.rssi);
    }
    if (magCopy.pending) {
      printMagCalPacket(magCopy.packet, magCopy.rssi);
    }
  }
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void onDataRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  int rssi = -127;
  if (info != nullptr && info->rx_ctrl != nullptr) {
    rssi = info->rx_ctrl->rssi;
  }
  handleEspNowData(data, len, rssi);
}
#else
void onDataRecv(const uint8_t *mac, const uint8_t *data, int len) {
  (void)mac;
  handleEspNowData(data, len, -127);
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
  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastMac, 6);
  peerInfo.channel = WIFI_CHANNEL;
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);
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
  setupFx();
  delay(250);
  Serial.println();
  Serial.print("BRIDGE_BOOT,reset_reason=");
  Serial.println((int)esp_reset_reason());
  Serial.println("Soupocalypse bridge ready");
  beginRadar(RADAR_BAUD);
  setupEspNow();
}

void loop() {
  readRadar();
  flushEspNowPackets();
  readLaptopSerial();
  maybeCycleRadarBaud();
  printRadarStatus();
  updateFx();
  delay(1);
}
