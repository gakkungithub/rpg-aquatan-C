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