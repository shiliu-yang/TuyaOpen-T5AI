// Copyright 2020-2021 Beken
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

#define TAG "dwtd"

#include <stdlib.h>
#include <string.h>
#include <common/bk_include.h>
#include "bk_arm_arch.h"
#include "armstar.h"
#include "components/log.h"
#include "debug_monitor_exception.h"
#include "bk_cli.h"
#include "bk_uart.h"
#include "dwt.h"
#include "fpb.h"

#define LOGI(...) BK_LOGI(TAG, ##__VA_ARGS__)
#define LOGW(...) BK_LOGW(TAG, ##__VA_ARGS__)
#define LOGE(...) BK_LOGE(TAG, ##__VA_ARGS__)
#define LOGD(...) BK_LOGD(TAG, ##__VA_ARGS__)

/*  "c":continue
 *  "s":single step
 *  "r":read 4 bytes, the format:r addr
 *  "w":write 4 bytes, the format:w addr value
 */
static char shell_buf[SHELL_BUF_CNT + 1] = {0};
static E_DEBUG_STATE s_user_requested_debug_state = DEBUG_STATE_NONE;

void dump_shell_buf(char *buf, uint32_t cnt)
{
    print_hex_dump("shell_buf of debugMonitor: ", buf, cnt);
}

uint32_t shell_port_line(char *token, uint32_t *addr, uint32_t *value)
{
    uint32_t rx_id = 0, about_to_end_flag = 0;
    uint32_t ret = 0, rx_over_flag = 0;
    char ch = 0, leading_ch = 0;
    char *str_addr, *str_val;
    
    /* [TODO] backup rx interrupt status, and resore the rx interrup based on the privious status*/
    bk_uart_disable_rx_interrupt(CLI_UART);
    /* waiting for user request*/
    while(BK_OK != uart_read_ready(CLI_UART))
    {
        ;
    }
    
    while((0 == rx_over_flag) && (rx_id < SHELL_BUF_CNT))
    {
        if(0 != uart_read_byte_ex(CLI_UART, (uint8_t *)&ch))
        {
            /* fifo does not has valid data*/
            if(about_to_end_flag)
            {
                rx_over_flag = 1;
                break;
            }
            else
            {
                /* if no CRLF, system will waiting for all user request*/
                continue;
            }
        }

        if((0 == ch) && (0 == rx_id))
        {
            /* discard leading spaces*/
        }
        else if((0x0d == ch) && (0 == rx_id))
        {
            ret = 1;
            leading_ch = 'e';       
        }
        else
        {
            shell_buf[rx_id ++] = ch;
        }
        
        if(('\n' == ch) || ('\r' == ch))
        {
            /* if a carriage return or line feed(CRLF) is received, the reception is 
             * about to end for all data must still be received completely
             */
            about_to_end_flag = 1;
        }
    }

    shell_buf[rx_id] = ch;

    if('e' == leading_ch)
    {
        /* enter char, and exit*/
        *token = leading_ch;
    }
    else if(rx_id)
    {
        leading_ch = shell_buf[0];
        *token = leading_ch;
    }
    else
    {
        goto failed_exit;
    }
    
    dump_shell_buf(shell_buf, rx_id);

    if(('c' == leading_ch) || ('s' == leading_ch))
    {
        ret = 1;
    }
    else if('r' == leading_ch)
    {
        str_addr = strtok(&shell_buf[2], " ");
        if(NULL != str_addr)
        {
            *addr = strtoll(str_addr, NULL, 16);
            ret = 1;
        }
    }
    else if('w' == leading_ch)
    {
        str_addr = strtok(&shell_buf[2], " ");
        str_val = strtok(NULL, " ");
        if((NULL != str_addr) && (NULL != str_val))
        {
            *addr = strtoll(str_addr, NULL, 16);
            *value = strtoll(str_val, NULL, 16);
            ret = 1;
        }
    }

failed_exit:
    bk_uart_enable_rx_interrupt(CLI_UART);

    return ret;
}

void fpb_enable(void)
{
    fpb_enable_breakpoint_unit();
}

void fpb_disable(void)
{
    fpb_disable_breakpoint_unit();
}

void debug_monitor_handler_c(CONTEXT_FRAME_T *frame)
{
    /* DFSR: debug fault status register
     *       bit 0: HALTED: halt or step event
     *       bit 1: BKPT: breakpoint event
     *       bit 2: DWTTRAP: watchpoint event
     *       bit 3: VCATCH: vector catch debug event
     *       bit 4: EXTERNAL: external debug request debug event
     */
    const uint32_t is_dwt_dbg_evt = (SCB->DFSR & SCB_DFSR_DWTTRAP_Msk);
    const uint32_t is_bkpt_dbg_evt = (SCB->DFSR & SCB_DFSR_BKPT_Msk);
    const uint32_t is_halt_dbg_evt = (SCB->DFSR & SCB_DFSR_HALTED_Msk);
    int log_sync_flag = bk_get_printf_sync();

    bk_set_printf_sync(1);
    LOGI("\r\n\r\n\r\nDebugMonitor Exception\r\n");

    LOGI("DEMCR: 0x%08x\r\n", DCB->DEMCR);
    LOGI("DFSR:  0x%08x (bkpt=%d, halt=%d, dwt=%d)\r\n", SCB->DFSR,
              (int)is_bkpt_dbg_evt, (int)is_halt_dbg_evt,
              (int)is_dwt_dbg_evt);

    LOGE("Register Dump:\r\n");
    LOGE("    r0  =0x%08x\r\n", frame->r0);
    LOGE("    r1  =0x%08x\r\n", frame->r1);
    LOGE("    r2  =0x%08x\r\n", frame->r2);
    LOGE("    r3  =0x%08x\r\n", frame->r3);
    LOGE("    r12 =0x%08x\r\n", frame->r12);
    LOGE("    lr  =0x%08x\r\n", frame->lr);
    LOGE("    pc  =0x%08x\r\n", frame->return_address);
    LOGE("    xpsr=0x%08x\r\n", frame->xpsr);

    if (is_dwt_dbg_evt 
            || is_bkpt_dbg_evt 
            || (s_user_requested_debug_state == DEBUG_STATE_SINGLE_STEP))
    {
        LOGI("Debug Event Detected, Waiting for User Request:c/s/r addr/w addr value\r\n");
        while (1) 
        {
            char token;
            uint32_t addr = -1, val = -1;

            if (!shell_port_line(&token, &addr, &val)) 
            {
                continue;
            }

            LOGI("Got The Token '%c'\r\n", token);
            if (token == 'c') 
            { // 'c' == 'continue'
                s_user_requested_debug_state = DEBUG_STATE_NONE;
                break;
            }
            else if (token == 's') 
            { // 's' == 'single step'
                s_user_requested_debug_state = DEBUG_STATE_SINGLE_STEP;
                break;
            }
            else if (token == 'e') 
            {
                LOGE("\r\n");
            }
            else if (token == 'r') 
            {
                LOGE("read addr;0x%x, value:0x%x\r\n",addr, REG_READ(addr));
            }
            else if (token == 'w') 
            {
                LOGE("write addr;0x%x, value:0x%x\r\n",addr, val);
                REG_WRITE(addr, val);
                LOGE("read after write, addr;0x%x, value:0x%x\r\n",addr, REG_READ(addr));
            }
        }
    } 
    else
    {
        LOGI("Resuming ...\r\n");
    }

    if (is_bkpt_dbg_evt) 
    {
        LOGI("is_bkpt_dbg_evt ...\r\n");
        const uint16_t instruction = *(uint16_t*)frame->return_address;
        LOGE("instruction:0x%04x\r\n",instruction);
        if ((instruction & 0xff00) == 0xbe00) 
        {
          // advance past breakpoint instruction
          frame->return_address += sizeof(instruction);
        } 
        else 
        {
          // It's a FPB generated breakpoint
          // We need to disable the FPB and single-step
          fpb_disable();
          LOGI("Single-Stepping over FPB at 0x%x\r\n", frame->return_address);
        }

        // single-step to the next instruction
        // This will cause a DebugMonitor interrupt to fire
        // once we return from the exception and a single
        // instruction has been executed. The HALTED bit
        // will be set in the DFSR when this happens.
        DCB->DEMCR |= (DCB_DEMCR_MON_STEP_Msk);
        // We have serviced the breakpoint event so clear mask
        SCB->DFSR = SCB_DFSR_BKPT_Msk;
    } 
    else if (is_halt_dbg_evt) 
    {
        LOGI("is_halt_dbg_evt ...\r\n");
        // re-enable FPB in case we got here via single-step
        // for a BKPT debug event
        fpb_enable();

        if (s_user_requested_debug_state != DEBUG_STATE_SINGLE_STEP) 
        {
          DCB->DEMCR &= ~(DCB_DEMCR_MON_STEP_Msk);
        }
        else
        {
            DCB->DEMCR |= (DCB_DEMCR_MON_STEP_Msk);
        }

        // We have serviced the single step event so clear mask
        SCB->DFSR = SCB_DFSR_HALTED_Msk;
    } 
    else if (is_dwt_dbg_evt) 
    {
        LOGI("is_dwt_dbg_evt ...\r\n");

        if (s_user_requested_debug_state != DEBUG_STATE_SINGLE_STEP) 
        {
            DCB->DEMCR &= ~(DCB_DEMCR_MON_STEP_Msk);
            dwt_disable_debug_monitor_mode();
        }
        else
        {
            DCB->DEMCR |= (DCB_DEMCR_MON_STEP_Msk);
        }

        // Future exercise: handle DWT debug events
        SCB->DFSR = SCB_DFSR_DWTTRAP_Msk;
    }
    
    bk_set_printf_sync(log_sync_flag);
}
// eof

