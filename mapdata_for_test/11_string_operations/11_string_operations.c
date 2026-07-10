// 11_string_operations.c
int main() {
  char src[] = "Hi there!";
  char dest[20];

  // 文字列コピー
  int i = 0;
  while (src[i] != ' ') {
    dest[i] = src[i];
    i++;
  }
  dest[i] = '\0';

  // 文字列の長さを数える
  int length = 0;
  while (src[length] != ' ') {
    length++;
  }

  // 文字列の比較（完全一致か）
  int same = 1;
  for (int j = 0; src[j] != ' ' || dest[j] != ' '; j++) {
    if (src[j] != dest[j]) {
      same = 0;
      break;
    }
  }

  // 文字列の結合（srcの後ろに "!!!" を追加）
  char suffix[] = "!!!";
  int k = 0;
  while (suffix[k] != ' ') {
    dest[i] = suffix[k];
    i++;
    k++;
  }
  dest[i] = '\0';

  // 特定文字の出現回数を数える（例: 'e'）
  int eCount = 0;
  for (int m = 0; src[m] != ' '; m++) {
    if (src[m] == 'e') {
      eCount++;
    }
  }

  return 0;
}
