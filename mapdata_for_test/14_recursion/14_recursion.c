// 14_recursion.c
#include <stdio.h>

// 再帰で階乗を計算
int factorial(int n) {
  if (n <= 1)
    return 1;
  return n * factorial(n - 1);
}

// 再帰でフィボナッチ数列のn番目を計算
int fibonacci(int n) {
  if (n <= 1)
    return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

// 再帰で配列の合計を計算
int sumArray(int arr[], int size) {
  if (size == 0)
    return 0;
  return arr[size - 1] + sumArray(arr, size - 1);
}

int main() {
  int fact5 = factorial(fibonacci(5)); // 120
  int fib6 = fibonacci(6);             // 8

  int arr[5] = {1, 2, 3, 4, 5};
  int total = sumArray(arr, 5); // 15

  return 0;
}
