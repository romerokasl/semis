#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>

// ===== Pines =====
const int FOTO_PIN = A0;          // Fototransistor
const int VOLT_PIN = A1;          // Panel (voltaje sobre la resistencia)
const float RESISTENCIA = 40.0;   // Ohms

const int ONE_WIRE_BUS = 5;       // DS18B20 en D5
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

#define DHTPIN 3                  // DHT11 en D3
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// Valor que se envia cuando un sensor falla (el dashboard lo ignora)
const float ERROR_VAL = -999.0;

void setup() {
  Serial.begin(9600);   // USB y modulo Bluetooth LE a 9600
  ds18b20.begin();
  dht.begin();
}

void loop() {
  // Fototransistor
  int luz = analogRead(FOTO_PIN);

  // Voltaje y corriente (I = V / R)
  int adc = analogRead(VOLT_PIN);
  float volt = (adc * 5.0) / 1023.0;
  float corrienteMA = (volt / RESISTENCIA) * 1000.0;

  // DS18B20
  ds18b20.requestTemperatures();
  float tempDS = ds18b20.getTempCByIndex(0);
  if (tempDS == DEVICE_DISCONNECTED_C) tempDS = ERROR_VAL;

  // DHT11
  float hum = dht.readHumidity();
  float tempDHT = dht.readTemperature();
  if (isnan(hum)) hum = ERROR_VAL;
  if (isnan(tempDHT)) tempDHT = ERROR_VAL;

  // Una linea por lectura:
  // DATA,voltaje(V),corriente(mA),luz(0-1023),tempDS18B20(C),humedad(%),tempDHT11(C)
  Serial.print("DATA,");
  Serial.print(volt, 3);        Serial.print(',');
  Serial.print(corrienteMA, 2); Serial.print(',');
  Serial.print(luz);            Serial.print(',');
  Serial.print(tempDS, 2);      Serial.print(',');
  Serial.print(hum, 1);         Serial.print(',');
  Serial.println(tempDHT, 1);

  delay(2000);
}
