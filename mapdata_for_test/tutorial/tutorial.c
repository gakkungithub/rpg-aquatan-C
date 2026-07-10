// tutorial.c
int testCheck(int t) {
  t += 30;
  return t;
}

int main() {
  // ここで変数の説明
  int test = 30;
  // 変数の違いとアイテムウィンドウを説明(次のアクションのために、条件文の説明をする)
  char c = 'a';

  // 条件文の説明(井戸やキャラクターの説明)
  if (c == 'f') {
    test = 0;
    // 条件によって行くところが違うことの説明
  } else {
    // 計算式の説明
    // 次のためにコマンドウィンドウの説明(cで開くなど)
    test = 80;
  }

  // 関数についての説明をする(飛ばさないなら他の場所に遷移することを説明する)
  int finalResult = testCheck(test);

  // 戻り値の説明をする
  return 0;
}
