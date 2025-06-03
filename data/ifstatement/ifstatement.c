int main() {
  int i = 3, j = 4;
  if (i == 4) {
    j *= 2;

  } else if (i < 5) {
    j++;

  } else {
    j--;
  }

  return ++j;
}