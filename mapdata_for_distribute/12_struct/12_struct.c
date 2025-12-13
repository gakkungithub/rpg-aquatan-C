// 12_struct.c
#include <stdio.h>
#include <string.h>

// 構造体の定義
struct Person {
  char name[20];
  int age;
  float height;
  double weight;
};

float getFloat(int i) { return (float)i; }

int getAge(int i) { return i + 10; }

int main() {
  // 初期化と代入
  struct Person p1 = {{'K', 'e', 'n', '\0'}, 23, 2, 68.5};

  struct Person p2;
  strcpy(p2.name, "Hana");
  p2.age = 35;
  p2.height = 162.5f;
  p2.weight = 55.0;

  // メンバの一部だけコピー
  struct Person p3 = p2;
  p3.age += 1;
  strcpy(p3.name, "Yuki");

  // 配列として構造体を管理
  struct Person people[3] = {p1, p2, p3};

  return 0;
}
