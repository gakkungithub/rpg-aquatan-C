// 17_function_and_pointer.c
// 関数とポインタ（引数にポインタ）
void swap(int *a, int *b) {
  int tmp = *a;
  *a = *b;
  *b = tmp;
}

// 配列の要素の最大値をポインタを使って取得
int maxValue(int *arr, int size) {
  int max = *arr;
  for (int i = 1; i < size; i++) {
    if (*(arr + i) > max) {
      max = *(arr + i);
    }
  }
  return max;
}

// ポインタ引数で値を書き換える
void setValues(int *x, int *y, int val1, int val2) {
  *x = val1;
  *y = val2;
}

int main() {
  int x = 100, y = 200;
  swap(&x, &y); // x=200, y=100

  int numbers[] = {3, 9, 2, 8, 5};
  int max = maxValue(numbers, 5); // max=9

  int a, b;
  setValues(&a, &b, 10, 20); // a=10, b=20

  return 0;
}
