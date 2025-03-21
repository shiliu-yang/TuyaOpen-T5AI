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


#include <common/bk_include.h>
#include <driver/lcd_types.h>


#define LCD_QSPI_ST77903_H0165Y008T_REGISTER_WRITE_COMMAND      0xDE
#define LCD_QSPI_ST77903_H0165Y008T_REGISTER_READ_COMMAND       0xDD
#define LCD_QSPI_ST77903_H0165Y008T_HSYNC_COMMAND               0x60
#define LCD_QSPI_ST77903_H0165Y008T_VSYNC_COMMAND               0x61
#define LCD_QSPI_ST77903_H0165Y008T_VSW     (1)
#define LCD_QSPI_ST77903_H0165Y008T_HFP     (8)
#define LCD_QSPI_ST77903_H0165Y008T_HBP     (8)


static const lcd_qspi_init_cmd_t st77903_h0165y008t_init_cmds[] =
{
	{0x00, {0x14}, 0xff},
	{0x00, {0x78}, 0xff},
	{0xf0, {0xc3}, 1},
	{0xf0, {0x96}, 1},
	{0xf0, {0xa5}, 1},
	{0xe9, {0x20}, 1},
	{0xe7, {0x80, 0x77, 0x1f, 0xcc}, 4},
	{0xc1, {0x77, 0x07, 0xcf, 0x16}, 4},
	{0xc2, {0x77, 0x07, 0xcf, 0x16}, 4},
	{0xc3, {0x22, 0x02, 0x22, 0x04}, 4},
	{0xc4, {0x22, 0x02, 0x22, 0x04}, 4},
	{0xc5, {0xed}, 1},
	{0xe0, {0x87, 0x09, 0x0c, 0x06, 0x05, 0x03, 0x29, 0x32, 0x49, 0x0f, 0x1b, 0x17, 0x2a, 0x2f}, 14},
	{0xe1, {0x87, 0x09, 0x0c, 0x06, 0x05, 0x03, 0x29, 0x32, 0x49, 0x0f, 0x1b, 0x17, 0x2a, 0x2f}, 14},
	{0xe5, {0xbe, 0xf5, 0xb1, 0x22, 0x22, 0x25, 0x10, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22}, 14},
	{0xe6, {0xbe, 0xf5, 0xb1, 0x22, 0x22, 0x25, 0x10, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22}, 14},
	{0xec, {0x40, 0x03}, 2},
	{0x36, {0x0c}, 1},
#if (CONFIG_LCD_QSPI_COLOR_DEPTH_BYTE == 3)
	{0x3a, {0x07}, 1},  //#07-RGB888
#else
	{0x3a, {0x05}, 1},  //#05-RGB565
#endif
	{0xb2, {0x00}, 1},
	{0xb3, {0x01}, 1},
	{0xb4, {0x00}, 1},
	{0xb5, {0x00, 0x08, 0x00, 0x08}, 4},
	{0xa5, {0x00, 0x00, 0x00, 0x00, 0x00, 0x15, 0x2a, 0x8a, 0x02}, 9},
	{0xa6, {0x00, 0x00, 0x00, 0x00, 0x00, 0x15, 0x2a, 0x8a, 0x02}, 9},
	{0xba, {0x0a, 0x5a, 0x23, 0x10, 0x25, 0x02, 0x00}, 7},
	{0xbb, {0x00, 0x30, 0x00, 0x2c, 0x82, 0x87, 0x18, 0x00}, 8},
	{0xbc, {0x00, 0x30, 0x00, 0x2c, 0x82, 0x87, 0x18, 0x00}, 8},
	{0xbd, {0xa1, 0xb2, 0x2b, 0x1a, 0x56, 0x43, 0x34, 0x65, 0xff, 0xff, 0x0f}, 11},
	{0x35, {0x00}, 1},
	{0x21, {0x00}, 0},
	{0x11, {0x00}, 0},
	{0x00, {0x78}, 0xff},
	{0x29, {0x00}, 0},
	//    {0xb0, {0xa5}, 1},
	//    {0xcc, {0x40, 0x00, 0x3f, 0x00, 0x14, 0x14, 0x20, 0x20, 0x03}, 9},
};

static uint8_t st77903_h0165y008t_cmd[4] = {0xDE, 0x00, 0x60, 0x00};

static const lcd_qspi_t lcd_qspi_st77903_h0165y008t_config =
{
	.clk = LCD_QSPI_48M, // MAX CLK is 50M
	.refresh_method = LCD_QSPI_REFRESH_BY_LINE,
	.reg_write_cmd = LCD_QSPI_ST77903_H0165Y008T_REGISTER_WRITE_COMMAND,
	.reg_read_cmd = LCD_QSPI_ST77903_H0165Y008T_REGISTER_READ_COMMAND,
	.reg_read_config.dummy_clk = 0,
	.reg_read_config.dummy_mode = LCD_QSPI_NO_INSERT_DUMMMY_CLK,
	.pixel_write_config.cmd = st77903_h0165y008t_cmd,
	.pixel_write_config.cmd_len = sizeof(st77903_h0165y008t_cmd),
	.init_cmd = st77903_h0165y008t_init_cmds,
	.device_init_cmd_len = sizeof(st77903_h0165y008t_init_cmds) / sizeof(lcd_qspi_init_cmd_t),

	.refresh_config.hsync_cmd = LCD_QSPI_ST77903_H0165Y008T_HSYNC_COMMAND,
	.refresh_config.vsync_cmd = LCD_QSPI_ST77903_H0165Y008T_VSYNC_COMMAND,
	.refresh_config.vsw = LCD_QSPI_ST77903_H0165Y008T_VSW,
	.refresh_config.hfp = LCD_QSPI_ST77903_H0165Y008T_HFP,
	.refresh_config.hbp = LCD_QSPI_ST77903_H0165Y008T_HBP,
#if (CONFIG_LCD_QSPI_COLOR_DEPTH_BYTE == 3)
	.refresh_config.line_len = (PPI_400X400 >> 16) * 3,
	.frame_len = (PPI_400X400 >> 16) * 3 * (PPI_400X400 & 0xFFFF),
#else
	.refresh_config.line_len = (PPI_400X400 >> 16) * 2,
	.frame_len = (PPI_400X400 >> 16) * 2 * (PPI_400X400 & 0xFFFF),
#endif
};

//st77903 screen without display ram, and need to send data continuously.
const lcd_device_t lcd_device_st77903_h0165y008t =
{
	.id = LCD_DEVICE_ST77903_H0165Y008T,
	.name = "st77903_h0165y008t",
	.type = LCD_TYPE_QSPI,
	.ppi = PPI_400X400,
	.qspi = &lcd_qspi_st77903_h0165y008t_config,
	.init = NULL,
	.lcd_off = NULL,
};


