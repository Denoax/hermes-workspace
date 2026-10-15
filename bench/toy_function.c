#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
static uint32_t owned_transform(uint32_t x) {
    return (x * UINT32_C(3) + UINT32_C(7)) ^ UINT32_C(0x5A);
}
int main(void) {
    uint32_t x;
    while (scanf("%" SCNu32, &x) == 1) {
        printf("%" PRIu32 "\n", owned_transform(x));
    }
    return 0;
}
