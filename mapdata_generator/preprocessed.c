# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C/data/functions/functions.c"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 418 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C/data/functions/functions.c" 2
int funcA(void){
    int c = 2, d = 3;
    c++;
    d--;
    return c * d;
}

void funcB(int i, char j);

int main(){
    int i = 3;
    char h = 4;
    h++;
    funcB(i, h);
    return funcA();
}

void funcB(int i, char j){
    int h = i * j;
    h--;
}
