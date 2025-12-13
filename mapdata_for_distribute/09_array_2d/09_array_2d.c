// 09_array_2d.c
int add(int i, int j) { return i + j; }

int sub(int i, int j) { return i - j; }

int main() {
  int mat[3][3] = {{0 + 1, 2, 3}, {4, 5 - 3 + 3, 6}, {7, 8, 9}};

  int sum = add(add(4, 5), 2) + sub(3, 4);
  for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 3; j++) {
      sum += mat[i][j];
    }
  }

  int diagSum = 0;
  for (int i = 0; i < 3; i++) {
    diagSum += mat[i][i];
  }

  int transposed[3][3];
  for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 3; j++) {
      transposed[j][i] = mat[i][j];
    }
  }
  return 0;
}
