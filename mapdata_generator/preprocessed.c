# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C-1/data/01_int_variables/01_int_variables.c"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 418 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C-1/data/01_int_variables/01_int_variables.c" 2

int main() {
  int a = 5, d = 4;
  int b = 3;
  int c = a + b;

  const int sum = a + b;
  int difference = a - b;
  int product = a * b;
  int quotient = a / b;
  int remainder = a % b;

  a += 2;
  b *= 3;

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
