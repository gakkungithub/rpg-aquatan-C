# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C-1/data/switchstatement/switchstatement.c"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 418 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "/Users/gakkungt/Desktop/Developing_apps/university/graduate_experiment/rpg-aquatan-C-1/data/switchstatement/switchstatement.c" 2
int main(){
    int i = 3, j;
    switch(i){
        case 1:
            j = i;
            break;
        case 3:
            j = i * 2;
            break;
        default:
            j = i / 2;
            break;
    }
    return j;
}
