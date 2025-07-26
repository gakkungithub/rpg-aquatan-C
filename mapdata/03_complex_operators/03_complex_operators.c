// 03_complex_operators.c
int main() {
  int x = 10;
  int y = 3;
  int z;

  // インクリメント・デクリメント
  x++; // x = 11
  y--; // y = 2

  // 複合代入
  x += 5; // x = 16
  y *= 2; // y = 4

  // 複雑な式と優先順位
  z = x + y * 2;   // 掛け算優先
  z = (x + y) * 2; // 括弧で制御

  // インクリメントとデクリメントの前置/後置
  int a = 5;
  int b = a++; // b=5, a=6
  int c = ++a; // a=7, c=7

  // 三項演算子と複合式
  int max = (x > y) ? x : y;
  int min = (x < y) ? x : y;

  // 複数の演算を組み合わせ
  int complex = (x++ * 2) + (--y / 2);

  return 0;
}
