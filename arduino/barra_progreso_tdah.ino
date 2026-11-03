/*
 * Barra de Progreso y Recompensa Visual para Asistente TDAH
 * Universidad Salesiana de Bolivia - Proyecto Integrador
 * Placa: Arduino UNO R3
 * 
 * Conexiones en Protoboard:
 * LED 1 (Paso 1) -> Pin 2 con resistencia de 220 ohms a GND
 * LED 2 (Paso 2) -> Pin 3 con resistencia de 220 ohms a GND
 * LED 3 (Paso 3) -> Pin 4 con resistencia de 220 ohms a GND
 */

const int PIN_LED1 = 2;
const int PIN_LED2 = 3;
const int PIN_LED3 = 4;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_LED1, OUTPUT);
  pinMode(PIN_LED2, OUTPUT);
  pinMode(PIN_LED3, OUTPUT);
  
  apagarTodos();
  // Animación inicial de prueba al arrancar
  animacionInicio();
}

void loop() {
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    
    if (comando == "P1") {
      digitalWrite(PIN_LED1, HIGH);
      digitalWrite(PIN_LED2, LOW);
      digitalWrite(PIN_LED3, LOW);
    } 
    else if (comando == "P2") {
      digitalWrite(PIN_LED1, HIGH);
      digitalWrite(PIN_LED2, HIGH);
      digitalWrite(PIN_LED3, LOW);
    } 
    else if (comando == "P3") {
      digitalWrite(PIN_LED1, HIGH);
      digitalWrite(PIN_LED2, HIGH);
      digitalWrite(PIN_LED3, HIGH);
    } 
    else if (comando == "WIN") {
      animacionCelebracion();
    } 
    else if (comando == "PAUSA") {
      animacionPausa();
    } 
    else if (comando == "OFF") {
      apagarTodos();
    }
  }
}

void apagarTodos() {
  digitalWrite(PIN_LED1, LOW);
  digitalWrite(PIN_LED2, LOW);
  digitalWrite(PIN_LED3, LOW);
}

void animacionInicio() {
  for (int i = 0; i < 2; i++) {
    digitalWrite(PIN_LED1, HIGH);
    delay(100);
    digitalWrite(PIN_LED2, HIGH);
    delay(100);
    digitalWrite(PIN_LED3, HIGH);
    delay(150);
    apagarTodos();
    delay(100);
  }
}

void animacionCelebracion() {
  // Parpadeo festivo de recompensa
  for (int i = 0; i < 6; i++) {
    digitalWrite(PIN_LED1, HIGH);
    digitalWrite(PIN_LED2, HIGH);
    digitalWrite(PIN_LED3, HIGH);
    delay(150);
    apagarTodos();
    delay(150);
  }
  // Dejar encendidos como muestra de tarea completada
  digitalWrite(PIN_LED1, HIGH);
  digitalWrite(PIN_LED2, HIGH);
  digitalWrite(PIN_LED3, HIGH);
}

void animacionPausa() {
  apagarTodos();
  // Pulso suave en LED 2 indicando descanso
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_LED2, HIGH);
    delay(400);
    digitalWrite(PIN_LED2, LOW);
    delay(400);
  }
}
