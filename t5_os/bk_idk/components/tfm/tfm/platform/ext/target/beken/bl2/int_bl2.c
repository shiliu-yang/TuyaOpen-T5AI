// Copyright 2022-2023 Beken
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "target_cfg.h"
#include "region.h"
#include "cmsis.h"
#include "boot_hal.h"
#include <stdio.h>
#include <components/log.h>

#define TAG "int"

void NMI_Handler(void)
{
	aon_pmu_hal_set_bl2_reset_reason(RESET_SOURCE_BOOTLOADER_NMI_WDT, true);
	BK_LOGE(TAG, "CPU Fault: NMI!\r\n");
}

void HardFault_Handler(void)
{
	aon_pmu_hal_set_bl2_reset_reason(RESET_SOURCE_BOOTLOADER_HARD_FAULT, true);
	BK_LOGE(TAG, "CPU Fault: HardFault!\r\n");
}

void MemManage_Handler(void)
{
	aon_pmu_hal_set_bl2_reset_reason(RESET_SOURCE_BOOTLOADER_MPU_FAULT, true);
	BK_LOGE(TAG, "CPU Fault: MemManage!\r\n");
}

void BusFault_Handler(void)
{
	aon_pmu_hal_set_bl2_reset_reason(RESET_SOURCE_BOOTLOADER_BUS_FAULT, true);
	BK_LOGE(TAG, "CPU Fault: BusFault!\r\n");
}


