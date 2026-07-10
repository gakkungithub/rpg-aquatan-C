// 02_scalar_operations.c
int main() {
  // 各種スカラー型の宣言と初期化
  char c = 'A';
  short s = 100;
  int i = 4;
  long l = 100000L;
  float f = 3.14f;
  double d = 2.5;
  long double ld = 1.23456789L;

  // 演算と型変換（暗黙的）
  double result1 = i + d; // int + double -> double
  double result2 = s + f; // short + float -> float
  float result3 = c + f;  // char + float -> float

  // 明示的な型変換
  int fromDouble = (int)d;
  char fromInt = (char)i;
  double forced = (double)(s + i);

  // 型サイズの確認（結果はprintfなどで表示可能）
  int size_c = sizeof(char);
  int size_s = sizeof(short);
  int size_i = sizeof(int);
  int size_l = sizeof(long);
  int size_f = sizeof(float);
  int size_d = sizeof(double);
  int size_ld = sizeof(long double);

  // 組み合わせた計算
  long double mix = c + s + i + l + f + d + ld;

  return 0;
}
