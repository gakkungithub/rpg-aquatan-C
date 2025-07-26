int funcA(void) {
  int c = 2, d = 3;
  c++;
  d--;
  return c * d;
}

void funcB(int i, char j);

int main() {
  int i = 3;
  char h = 4;
  h++;
  funcB(i, h);
  return funcA();
}

void funcB(int i, char j) {
  int h = i * j;
  h--;
}
