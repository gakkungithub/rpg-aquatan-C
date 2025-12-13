// 10_string_and_char_array.c
int main() {
  // 文字列の初期化 (明示的に'\0'を含む)
  char name1[] = {'A', 'l', 'i', 'c', 'e', '\0'};

  // 文字列リテラルを用いた初期化 ('\0'が自動で追加される)
  char name2[] = "Bob";

  // 1文字を取り出して操作
  char firstLetter = name1[0];
  char lastLetter = name1[4];

  // 配列の長さを計算 ('\0'を含まない文字数)
  int length = 0;
  while (name1[length] != '\0') {
    length++;
  }

  // 大文字に変換
  for (int i = 0; name2[i] != '\0'; i++) {
    if (name2[i] >= 'a' && name2[i] <= 'z') {
      name2[i] = name2[i] - ('a' - 'A');
    }
  }

  // 2次元配列
  char names[3][10] = {"Tom", "Jerry", "Spike"};

  // 全ての文字列の1文字目を確認
  for (int i = 0; i < 3; i++) {
    char initial = names[i][0];
  }

  return 0;
}
