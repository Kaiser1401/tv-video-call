/*Read button panel and send over serial.
  Receive over serial and switch lights
 */


// panel: Blue, White, Yellow, Red, Green
// all pressed = 110 11111
// all on      = 101 11111

// presses preamble 110 (send), lights preamble 101 (receive)


// digital pin 2 has a pushbutton attached to it. Give it a name:
int btBlue   = 11;
int ledBlue  = 12;
int btWhite  = 9;
int ledWhite = 10;
int btYello  = 7;
int ledYello = 8;
int btRed    = 5;
int ledRed   = 6;
int btGreen  = 3;
int ledGreen = 4;

bool bEchoButtons = true;


// the setup routine runs once when you press reset:
void setup() {
  // initialize serial communication at 9600 bits per second:
  Serial.begin(9600);
  // make the pushbutton's pin an input:
  pinMode(btBlue, INPUT_PULLUP);
  pinMode(btWhite, INPUT_PULLUP);
  pinMode(btYello, INPUT_PULLUP);
  pinMode(btRed, INPUT_PULLUP);
  pinMode(btGreen, INPUT_PULLUP);
  
  pinMode(ledBlue, OUTPUT);
  pinMode(ledWhite, OUTPUT);
  pinMode(ledYello, OUTPUT);
  pinMode(ledRed, OUTPUT);
  pinMode(ledGreen, OUTPUT);
}


byte get_buttons()
{
  byte res = 0b00100000; // negatet 3bit header
  res |= digitalRead(btBlue) << 4;
  res |= digitalRead(btWhite) << 3;
  res |= digitalRead(btYello) << 2;
  res |= digitalRead(btRed) << 1;
  res |= digitalRead(btGreen) << 0;
  res = ~res;
  return res;
}


void set_buttons(byte lights)
{
  digitalWrite(ledBlue,lights & (1 << 4));
  digitalWrite(ledWhite,lights & (1 << 3));
  digitalWrite(ledYello,lights & (1 << 2));
  digitalWrite(ledRed,lights & (1 << 1));
  digitalWrite(ledGreen,lights & (1 << 0));
}

byte leds = 0;
// the loop routine runs over and over again forever:
void loop() {
  // read buttons
  byte buttons = get_buttons();
   // send buttons 
  Serial.write(buttons);
  if (Serial.available() >0)
  {
    leds = Serial.read();
    if ((leds & 0b10100000) != 0b10100000)
    {
      // wrong header, reset leds
      leds = 0;
      bEchoButtons = true;
    }
    else
    {
      bEchoButtons = false;
    }
  }

  if (bEchoButtons)
  {
    leds = buttons;
  }
  // set leds
  set_buttons(leds);
  delay(20); // 50 Hz
}



