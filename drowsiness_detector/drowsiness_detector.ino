#include <WiFi.h>
#include <WebServer.h>

// --- Wi-Fi Credentials ---
const char* ssid = "DG";
const char* password = "1234567asdf";

WebServer server(80);

// --- Pin Definitions ---
const int mq3DigitalPin = 34; 
const int buzzerPin = 13;
const int in1 = 26;
const int in2 = 27;
const int enA = 14; 

// --- State Variables ---
String driverState = "SAFE";  
unsigned long lastBlinkTime = 0;
unsigned long lastDecelTime = 0; 
unsigned long lastStutterTime = 0; // NEW: Tracks the stutter intervals
int currentSpeed = 255;
bool buzzerState = false;
bool isStutterBraking = false;     // NEW: Toggles between moving and braking

void setup() {
  Serial.begin(115200);
  
  pinMode(mq3DigitalPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);
  pinMode(enA, OUTPUT); 

  // Connect to Wi-Fi
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // --- Web Server Routes ---
  server.on("/safe", []() {
    driverState = "SAFE";
    currentSpeed = 255; 
    server.send(200, "text/plain", "Driver Awake");
  });
  
  server.on("/drowsy", []() {
    driverState = "DROWSY";
    server.send(200, "text/plain", "Driver Drowsy");
  });
  
  server.on("/sleeping", []() {
    driverState = "SLEEPING";
    server.send(200, "text/plain", "Driver Asleep!");
  });

  server.begin();
}

void loop() {
  server.handleClient(); 

  int isDrunk = digitalRead(mq3DigitalPin);

  // ---------------------------------------------------------
  // 1. HARD OVERRIDE: MQ3 Sensor (Instant Stop)
  // ---------------------------------------------------------
  if (isDrunk == LOW) { 
    analogWrite(enA, 0); 
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    digitalWrite(buzzerPin, HIGH); 
    return; 
  }

  // ---------------------------------------------------------
  // 2. CAMERA LOGIC: Safe, Drowsy, or Sleeping
  // ---------------------------------------------------------
  if (driverState == "SAFE") {
    analogWrite(enA, 255); 
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
    digitalWrite(buzzerPin, LOW); 
  } 
  
  else if (driverState == "DROWSY") {
    // A. Moves and breaks continuously (Stutter effect)
    // Toggles every 600 milliseconds
    if (millis() - lastStutterTime >= 250) {
      lastStutterTime = millis();
      isStutterBraking = !isStutterBraking; // Flip between true/false
    }

    if (isStutterBraking) {
      currentSpeed = 80;  // The low "braking" speed (adjust to be lower or higher as needed)
    } else {
      currentSpeed = 255; // The top speed
    }

    analogWrite(enA, currentSpeed);
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);

    // B. Blinking Buzzer (beeps every 300ms)
    if (millis() - lastBlinkTime >= 300) {
      lastBlinkTime = millis();
      buzzerState = !buzzerState; 
      digitalWrite(buzzerPin, buzzerState ? HIGH : LOW);
    }
  } 
  
  else if (driverState == "SLEEPING") {
    // A. Gradual Braking to a Halt
    if (millis() - lastDecelTime >= 50) { 
      lastDecelTime = millis();
      if (currentSpeed > 0) {
        currentSpeed -= 5; 
        if (currentSpeed < 0) currentSpeed = 0; 
      }
    }
    
    analogWrite(enA, currentSpeed); 

    // Cut motor logic completely when stopped
    if (currentSpeed == 0) {
      digitalWrite(in1, LOW);
      digitalWrite(in2, LOW);
    } else {
      digitalWrite(in1, HIGH);
      digitalWrite(in2, LOW);
    }

    // B. Fast Panic Blinking (beeps every 100ms)
    if (millis() - lastBlinkTime >= 100) {
      lastBlinkTime = millis();
      buzzerState = !buzzerState; 
      digitalWrite(buzzerPin, buzzerState ? HIGH : LOW);
    }
  }
  
  delay(10); 
}