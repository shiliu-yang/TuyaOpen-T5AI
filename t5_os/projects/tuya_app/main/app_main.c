#include "bk_private/bk_init.h"
#include <components/system.h>
#include <components/ate.h>
#include <os/os.h>
#include <components/shell_task.h>
#include "tuya_cloud_types.h"
#include "FreeRTOS.h"

#include "media_service.h"


#if (CONFIG_SYS_CPU0)
#include "driver/pwr_clk.h"
#include "modules/pm.h"
#endif

extern void rtos_set_user_app_entry(beken_thread_function_t entry);
extern void tkl_system_sleep(const uint32_t num_ms);

#include "FreeRTOS.h"
#include "task.h"
#include "tkl_system.h"
#include "tkl_watchdog.h"
#include "driver/wdt.h"

#if (CONFIG_SYS_CPU0)
TaskHandle_t __wdg_handle;
static void __feed_wdg(void *arg)
{
#define WDT_TIME    30000
    TUYA_WDOG_BASE_CFG_T cfg = {.interval_ms = WDT_TIME};
    tkl_watchdog_init(&cfg);

    while (1) {
        tkl_watchdog_refresh();
        tkl_system_sleep(WDT_TIME / 2);
    }
}

void user_app_main(void)
{

}
#endif

#if (CONFIG_SYS_CPU1)
extern void tuya_app_main(void);

void entry_tuya_app(void)
{
    // disable shell echo for gpio test
    shell_echo_set(0);

    bk_printf("-------- left heap: %d, reset reason: %x\r\n",
            xPortGetFreeHeapSize(), bk_misc_get_reset_reason() & 0xFF);
    // extern int tuya_upgrade_main(void);
    extern void tuya_app_main(void);
    // extern TUYA_OTA_PATH_E tkl_ota_is_under_seg_upgrade(void);

    // if(TUYA_OTA_PATH_INVALID != tkl_ota_is_under_seg_upgrade()) {
    //     bk_printf("goto tuya_upgrade_main\r\n");
    //     // tuya_upgrade_main();
    // }else {
        bk_printf("go to tuya\r\n");
        tuya_app_main();
    // }
}
#endif

int main(void)
{
#if (CONFIG_SYS_CPU0)
    if (!ate_is_enabled()) {
        rtos_set_user_app_entry((beken_thread_function_t)user_app_main);
    } else {
        // in ate mode, feed dog
        xTaskCreate(__feed_wdg, "feed_wdg", 1024, NULL, 6, (TaskHandle_t * const )&__wdg_handle);
    }
#endif // CONFIG_SYS_CPU0

	bk_init();
    media_service_init();

    extern OPERATE_RET tuya_ipc_init(void);
    tuya_ipc_init();

#if (CONFIG_SYS_CPU0)
    bk_printf("\r\nstart cp1\r\n");
    bk_pm_module_vote_boot_cp1_ctrl(PM_BOOT_CP1_MODULE_NAME_APP, PM_POWER_MODULE_STATE_ON);

#if (CONFIG_TUYA_TEST_CLI)
    extern int cli_tuya_test_init(void);
    cli_tuya_test_init();
#endif

#endif // CONFIG_SYS_CPU0

#if (CONFIG_SYS_CPU1)
    bk_printf("\r\nstart tuya_app_main\r\n");
    entry_tuya_app();
    // TUYA_LwIP_Init(); // If debugging and tuya_app_main is commented out, you need to initialize lwip, as the underlying MAC data processing requires pbuf resources
#endif
    return 0;
}
