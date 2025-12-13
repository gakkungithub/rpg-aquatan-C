// 19_file_io.c
#include <stdio.h>

// ファイルへの書き込みと読み込み
int main() {
  FILE *fp = fopen("sample.txt", "w");
  if (!fp) {
    fprintf(stderr, "ファイル書き込み用に開けませんでした。");
    return 1;
  }

  fprintf(fp, "Hello File!");
  fclose(fp);

  fp = fopen("sample.txt", "r");
  if (!fp) {
    fprintf(stderr, "ファイル読み込み用に開けませんでした。");
    return 1;
  }

  char line[100];
  int number;

  if (fgets(line, sizeof(line), fp) != NULL) {
    printf("読み込んだ文字列: %s", line);
  }

  if (fscanf(fp, "%d", &number) == 1) {
    printf("読み込んだ数値: %d", number);
  } else {
    fprintf(stderr, "数値の読み取りに失敗しました。");
  }

  fclose(fp);
  return 0;
}
