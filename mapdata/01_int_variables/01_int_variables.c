// 01_int_variables.c
int main() {
  int a = 5;
  int b = 3;
  int c = a + b;

  const int sum = a + b;
  int difference = a - b;
  int product = a * b;
  int quotient = a / b;
  int remainder = a % b;

  a += 2; // a = a + 2
  b *= 3; // b = b * 3

  // test
  int temp = a;
  a = b;
  b = temp;

  int max = (a > b) ? a : b;
  int min = (a < b) ? a : b;

  int complex = (a + b) + (c - a) / (b + 1);

  int neg = -a;
  int abs_like = (neg < 0) ? -neg : neg;

  return 0;
}
