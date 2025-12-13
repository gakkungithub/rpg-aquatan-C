// 08_array_1d.c
int main() {
  int arr[10];

  // 各要素に値を代入（インデックスの2乗）
  for (int i = 0; i < 10; i++) {
    arr[i] = i * i;
  }

  // 配列の内容を使って演算
  int sum = 0;
  int max = arr[0];
  int min = arr[0];
  for (int i = 0; i < 10; i++) {
    sum += arr[i];
    if (arr[i] > max)
      max = arr[i];
    if (arr[i] < min)
      min = arr[i];
  }

  // 配列の一部を書き換える
  arr[5] = 100;
  arr[7] = arr[2] + arr[3];

  // 特定の条件に合う要素の数を数える
  int evenCount = 0;
  for (int i = 0; i < 10; i++) {
    if (arr[i] % 2 == 0)
      evenCount++;
  }

  // 要素を逆順にコピー
  int reversed[10];
  for (int i = 0; i < 10; i++) {
    reversed[i] = arr[9 - i];
  }

  return 0;
}
