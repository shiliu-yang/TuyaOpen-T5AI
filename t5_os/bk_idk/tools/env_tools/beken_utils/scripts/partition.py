#!/usr/bin/env python3
import os
import json
import logging
import shutil
import re
import copy
import hashlib
import math
import csv
from enum import Enum
import sys
from .crc import *
from .common import *
from .security import *
from .ota import *
from .parse_csv import *
from .save_cmd import *

SZ_16M = 0x1000000
FLASH_SECTOR_SZ = 0x1000
CRC_UNIT_DATA_SZ = 32
CRC_UNIT_TOTAL_SZ = 34
GLOBAL_HDR_LEN = 32
IMG_HDR_LEN = 32
HDR_SZ = 0x1000
TAIL_SZ = 0x1000

flags_mapping = {
    "encrypted"   : 0,
    "flash_encrypted" : 1,
    "bk_2"        : 2,
    "bk_3"        : 3,
    "bk_4"        : 4,
    "bk_5"        : 5,
    "bk_6"        : 6,
    "bk_7"        : 7,
    # More internal flags can be added within the range of [0 ~ 7]
    "customer_8"  : 8,
    "customer_9"  : 9,
    "customer_10" : 10,
    "customer_11" : 11,
    "customer_12" : 12,
    "customer_13" : 13,
    "customer_14" : 14,
    "customer_15" : 15,
    # More customer flags can be added within the range of [8 ~ 15]
}

partition_keys_v2 = [
    'Name',
    'Type',
    'SubType',
    'Offset',
    'Size',
    'Flags',
]

partition_keys_v1 = [
    'Name',
    'Offset',
    'Size',
    'Execute',
    'Read',
    'Write'
]

class PartitionType(Enum):
    PARTITION_TYPE_APP  = 0X00
    PARTITION_TYPE_DATA = 0X01
    PARTITION_TYPE_ANY  = 0Xff

class PartitionSubType(Enum):
    PARTITION_SubType_BK_UNDEFINED_0   = 0X00
    PARTITION_SubType_BK_UNDEFINED_1   = 0X01
    PARTITION_SubType_BK_UNDEFINED_2   = 0X02
    PARTITION_SubType_BK_UNDEFINED_3   = 0X03
    PARTITION_SubType_BK_UNDEFINED_4   = 0X04
    PARTITION_SubType_BK_UNDEFINED_5   = 0X05
    PARTITION_SubType_BK_UNDEFINED_6   = 0X06
    PARTITION_SubType_BK_UNDEFINED_7   = 0X07
    PARTITION_SubType_BK_UNDEFINED_8   = 0X08
    PARTITION_SubType_BK_UNDEFINED_9   = 0X09
    PARTITION_SubType_BK_UNDEFINED_10  = 0X0a
    PARTITION_SubType_BK_UNDEFINED_11  = 0X0b
    PARTITION_SubType_BK_UNDEFINED_12  = 0X0c
    PARTITION_SubType_BK_UNDEFINED_13  = 0X0d
    PARTITION_SubType_BK_UNDEFINED_14  = 0X0e
    PARTITION_SubType_BK_UNDEFINED_15  = 0X0f

class Hdr:
    def __init__(self, magic, crc, version, hdr_len, img_num, flags = 0):
        self.magic = bytes.fromhex(magic)
        self.crc = bytes.fromhex(int2hexstr4(crc))
        self.version = bytes.fromhex(int2hexstr4(version))
        self.hdr_len = bytes.fromhex(int2hexstr2(hdr_len))
        self.img_num = bytes.fromhex(int2hexstr2(img_num))
        self.flags = bytes.fromhex(int2hexstr4(flags))
        self.reserved = bytes(0)

        logging.debug(f'global hdr: magic={self.magic}, version={self.version}, hdr_len={self.hdr_len}, img_num={self.img_num}, flags={self.flags}')

class Imghdr:
    def __init__(self, img_len, img_offset, flash_offset, crc, version, flags = 0):
        self.img_len = bytes.fromhex(int2hexstr4(img_len))
        self.img_offset = bytes.fromhex(int2hexstr4(img_offset))
        self.flash_offset = bytes.fromhex(int2hexstr4(flash_offset))
        self.crc = bytes.fromhex(int2hexstr4(crc))
        self.version = bytes.fromhex(int2hexstr4(version))
        self.flags = bytes.fromhex(int2hexstr4(flags))
        self.reserved = bytes(0)
        logging.debug(f'img hdr: img_len=%x, img_offset=%x, flash_offset=%x, crc=%x, version=%x flags=%x'
            %(img_len, img_offset, flash_offset, crc, version, flags))
 
class Partition:
    def is_overwrite(self):
        return self.ota_type == 'OVERWRITE'

    def is_xip(self):
        return self.ota_type == 'XIP'

    def is_out_of_range(self, addr):
        if (addr >= SZ_16M):
            return True 
        else:
            return False

    def is_app_partition(self):
        return (self.partition_type == 'app')

    def is_data_partition(self):
        return (self.partition_type == 'data')

    def is_flash_sector_aligned(self, addr):
        if ((addr % FLASH_SECTOR_SZ) == 0):
            return True
        else:
            return False

    def parse_raw_fields(self):
        self.partition_name = self.pdic['Name']
        self.partition_offset = self.pdic['Offset']
        self.partition_size = self.pdic['Size']

        if 'Type' in self.pdic:
            logging.debug(f'Partition csv v2.0')
            self.partition_type = self.pdic['Type']
            self.partition_subtype = self.pdic['SubType']
            self.partition_flags = self.pdic['Flags']
        else:
            logging.debug(f'Partition csv v1.0')
            self.partition_subtype = None
            self.partition_flags = None
            if self.pdic['Execute'] == 'TRUE':
                self.partition_type = 'app'
            else:
                self.partition_type = 'data'
 
        logging.debug(f'partition{self.idx} raw fields:')
        logging.debug(f'partition_name = {self.partition_name}')
        logging.debug(f'partition_type = {self.partition_type}')
        logging.debug(f'partition_subtype = {self.partition_subtype}')
        logging.debug(f'partition_offset = {self.partition_offset}')
        logging.debug(f'partition_size = {self.partition_size}')
        logging.debug(f'partition_flags = {self.partition_flags}')

    def is_bootloader_partition(self):
        if (self.partition_name.endswith("bootloader") or self.partition_name.endswith("bl2")):
            return True
        else:
            return False

    def find_partition_by_name(self, name):
        for p in self.partitions.partitions:
            if (name == p.partition_name):
                return p
        return None

    def parse_and_validate_bin_type(self):
        if self.is_app_partition():
            self.need_add_crc = True
        else:
            self.need_add_crc = False

        logging.debug(f'need_add_crc={self.need_add_crc}')
 
    def parse_and_validate_partition_name(self):
        reserved_partition_names = ['primary_all', 'secondary_all', 'all']
        secureboot_partitions = ['bl1_control', 'primary_manifest', 'secondary_manifest']

        if self.partition_name in reserved_partition_names:
            logging.error(f'Partition {self.partition_name} is reserved')
            exit(1)

        if self.partition_name in secureboot_partitions:
            if self.bl1_secureboot_en == False:
                logging.error(f'partition {self.partition_name} is reserved for secureboot')
                exit(1)

        self.pre_partition = None
        if self.idx != 0:
            self.pre_partition = self.partitions.partition_names[self.idx - 1]
        logging.debug(f'pre partition = {self.pre_partition}')

        self.file_name_prefix = self.partition_name
        self.primary_partition_name = None
        self.primary_partition = None
        self.is_secondary = False
        self.is_primary = False

        if pattern_match(self.partition_name, r"secondary_"):
            self.is_secondary = True
            self.primary_partition_name = self.partition_name.replace("secondary_", "primary_")
            self.primary_partition = self.find_partition_by_name(self.primary_partition_name)
            if self.primary_partition == None:
                logging.debug(f'Code partition {self.partition_name} has no primary partition')
                exit(1)
        elif pattern_match(self.partition_name, r"primary_"):
            self.is_primary = True

        if (self.is_app_partition() == False) and (self.is_primary or self.is_secondary) and (self.partition_name != 'primary_manifest') and (self.partition_name != 'secondary_manifest'):
            logging.error(f'Invalid data partition {self.partition_name}, prefix primary_/secondary is only for code partition')
            exit(1)

    def parse_and_validate_bin_name(self):
        self.bin_name = None
        self.bin_size = 0

        if (self.partition_name == 'bl1_control'):
            return

        if (self.partition_name == 'boot_flag'):
            self.bin_name = 'boot_flag.bin'
            return

        if (self.partition_name == 'primary_manifest'):
            self.bin_name = 'primary_manifest.bin'
            return

        if (self.partition_name == 'secondary_manifest'):
            self.bin_name = 'secondary_manifest.bin'
            return

        if (self.partition_name == 'bl2'):
            self.bin_name = 'bl2.bin'
            return

        if (self.partition_name == 'bl2_B'):
            self.bin_name = 'bl2_B.bin'
            return

        if (self.partition_name == 'ota'):
            return

        if self.is_data_partition():
            self.bin_name = f'{self.partition_name}.bin'
            return

        if (pattern_match(self.partition_name, r"primary_") == False) and (pattern_match(self.partition_name, r"secondary_") == False):
            logging.error(f'code partition {self.partition_name} should started with primary_ or secondary_')
            exit(1)

        self.bin_name = self.partition_name.replace("secondary_", "")
        self.bin_name = self.bin_name.replace("primary_", "")
        self.bin_name += '.bin'
        logging.debug(f'partition={self.partition_name}, bin_name={self.bin_name}')

    def parse_and_validate_verifier(self):
        self.bin_verifier = None
        self.bin_hdr_size = 0
        self.bin_tail_size = 0
 
        if self.is_data_partition():
            return

        if (self.partition_name == 'bl2'):
            if self.bl1_secureboot_en:
                self.bin_verifier = 'bl1'
        elif (self.bl2_exists) and (self.idx > self.bl2_partition_idx):
            self.bin_verifier = 'bl2'
            self.Dbus_en = True
            self.bin_hdr_size = crc_size(HDR_SZ)
            self.bin_tail_size = 0x1000
            if self.is_primary:
                self.partitions.append_primary_partitions_verified_by_bl2(self.partition_name)
            if self.is_secondary:
                self.partitions.append_secondary_partitions_verified_by_bl2(self.partition_name)

        logging.debug(f'bin verifier={self.bin_verifier}, bin_hdr_size={self.bin_hdr_size}, bin_tail_size={self.bin_tail_size}')


    def parse_and_validate_partition_offset(self):
        if self.partition_offset == '':
            self.partition_offset = self.deduced_min_partition_offset
        else:
            self.partition_offset = hex2int(self.partition_offset)

        if (self.idx == 0) and (self.partition_offset > 0):
            logging.error(f'first {self.partition_name} offset should be 0')
            exit(1)

        if (self.partition_offset < self.deduced_min_partition_offset):
            logging.error(f'partition{self.idx} partition {self.partition_name} offset=%x overlapped with {self.pre_partition}' %(self.partition_offset))
            exit(1)

        if (self.is_out_of_range(self.partition_offset) == True):
            logging.error(f'partition{self.idx} partition {self.partition_name} offset=%x is out of range' %(self.partition_offset))
            exit(1)

        if (self.is_app_partition()):
            if (self.is_flash_sector_aligned(self.partition_offset) == False):
                logging.error(f'partition{self.idx} partition {self.partition_name} offset=%x not FLASH sector aligned' %(self.phy_partition_offset))
                exit(1)

        logging.debug(f'partition{self.idx} {self.partition_name} partition_offset=%x' %(self.partition_offset))

    def parse_and_validate_partition_size(self):
        if self.partition_size == '':
            logging.error(f'Size of partition {self.partition_name} is not configured')
            exit(1)

        self.partition_size = size2int(self.partition_size)
        if (self.is_out_of_range(self.partition_size) == True):
            logging.error(f'partition{self.idx} partition {self.partition_name} size=%x out of range' %(self.partition_size))
            exit(1)

        if (self.is_flash_sector_aligned(self.partition_size) == False):
            logging.error(f'partition{self.idx} partition {self.partition_name} size=%x not FLASH sector aligned' %(self.partition_size))
            exit(1)

        if self.is_secondary:
            if (self.partition_size != self.primary_partition.partition_size):
                logging.error(f'Size of {self.partition_name} and {self.primary_partition.partition_name} not equal')
                exit(1)

        logging.debug(f'partition{self.idx} {self.partition_name} partition size=%x' %(self.partition_size))
 
    def parse_and_validate_partition_flags(self):
        flags_enum = 0
        if None == self.partition_flags:
            return
        flag_list = re.split(r'\s*\|\s*', self.partition_flags)

        for flag in flag_list:
            if flag in flags_mapping:
                flags_enum |= (1 << flags_mapping[flag])

        self.partition_flags = flags_enum

    def is_encrypted(self):
        if (self.partition_flags & (1 << flags_mapping['encrypted'])):
            return True
        else:
            return False

    def is_flash_encrypted(self):
        if (self.partition_flags & (1 << flags_mapping['flash_encrypted'])):
            return True
        else:
            return False

    def is_nvs(self):
        if self.partition_type == 'data' and self.partition_subtype == 'nvs':
            return True
        else:
            return False

    def is_nvs_key(self):
        if self.partition_type == 'data' and self.partition_subtype == 'nvs_key':
            return True
        else:
            return False

    def find_partition_by_name(self, name):
        for p in self.partitions.partitions:
            if (name == p.partition_name):
                return p
        return None

    '''
    +------------------------+  <--- partition_offset/bin_hdr_offset
    |  HDR (plain data)      |
    |  (bin_hdr_size)        |  
    |                        |
    +------------------------+  <--- bin_code_partition_offset
    |  vector/CRC aligned pad|
    |                        |
    +------------------------+  <--- bin_1st_instruction_offset
    |  Code (CRC/Encrypted)  |
    |                        |
    |                        |
    +------------------------+
    |  Unused                |
    |                        |
    +------------------------+  <--- bin_tail_offset
    |  TAIL (plain data)     |
    |  (bin_tail_size)       |
    |                        |
    +------------------------+  <--- partition end
    '''

    def check_68K_boundary(self):
        if not self.partitions.tfm_exists:
            logging.debug(f'TFM not exists, no need 68K aligned')
            return

        if (self.partition_name != 'primary_tfm_s') and (self.partition_name != 'ota'):
            return

        if self.partition_name == 'primary_tfm_s':
            p = self
        else:
            p = self.find_partition_by_name(self.pre_partition)

        s_ns_boundary = p.partition_offset + p.partition_size
        if (s_ns_boundary % (68<<10)) != 0:
            block = s_ns_boundary // (68<<10)
            suggest_boundary = (block + 1) * (68 << 10)
            diff = suggest_boundary - s_ns_boundary
            logging.error(f'NS start {s_ns_boundary/1024}, suggest start {suggest_boundary/1024}')
            logging.error(f'The offset of partition next to {p.partition_name} is %x, NOT in 68K boundary!' %(s_ns_boundary))
            size_k = p.partition_size/1024
            suggest_size_k = (p.partition_size + diff)/1024
            logging.error(f'Suggest to change {p.partition_name} partition size from {size_k}k to {suggest_size_k}k')
            exit(1)

    def calculate_offset(self,hdr_size):
        # Are the results of two branches the same?
        if self.Dbus_en:
            self.phy_partition_offset = ceil_align(self.partition_offset, CRC_UNIT_TOTAL_SZ)
            self.vir_partition_offset = phy2virtual(self.phy_partition_offset)
            self.vir_code_offset = ceil_align(self.vir_partition_offset + hdr_size,self.cpu_vector_align_bytes)
            self.phy_code_offset = virtual2phy(self.vir_code_offset)
        else:
            self.phy_partition_offset = self.partition_offset
            self.vir_partition_offset = phy2virtual(self.phy_partition_offset)
            phy_min_code_offset = self.phy_partition_offset + hdr_size
            vir_min_code_offset = phy2virtual(phy_min_code_offset)
            self.vir_code_offset = ceil_align(vir_min_code_offset,self.cpu_vector_align_bytes)
            self.phy_code_offset = virtual2phy(self.vir_code_offset)

        logging.debug(f'name = %s, phy_partition_offset= 0x%x, vir_partition_offset= 0x%x,vir_code_offset= 0x%x, phy_code_offset= 0x%x' 
                    %(self.partition_name,self.phy_partition_offset,self.vir_partition_offset,self.vir_code_offset,self.phy_code_offset))


    def calculate_size(self):
        self.partition_hdr_pad_size =self.phy_partition_offset - self.partition_offset
        self.partition_tail_pad_size = (self.partition_offset+self.partition_size) - floor_align(self.partition_offset+self.partition_size,34)
        self.phy_partition_size = self.partition_size - self.partition_hdr_pad_size - self.partition_tail_pad_size
        self.vir_partition_size = phy2virtual(self.phy_partition_size)
        self.phy_code_size = self.phy_partition_size - (self.phy_code_offset - self.phy_partition_offset)
        self.vir_code_size = phy2virtual(self.phy_code_size)

        logging.debug(f'phy_partition_size= 0x%x, vir_partition_size= 0x%x' %(self.phy_partition_size,self.vir_partition_size))


    def parse_and_validate_address(self):
        if (self.is_out_of_range(self.partition_offset + self.partition_size - 1) == True):
            logging.error(f'partition{self.idx} {self.partition_name} start=%x size=%x is out of range' %(self.partition_offset, self.partition_size))
            exit(1)

        if(self.is_app_partition()):
            if (self.is_secondary) and ((self.bin_verifier == "bl2") or (self.bin_verifier == "bl2_B")):
                if (self.primary_partition == None):
                    logging.error(f'partition{self.idx} {self.partition_name} missing primary partition')
                    exit(1)
                if (self.is_xip()):
                    if len(self.partitions.secondary_partitions_verified_by_bl2) == 1:
                        self.calculate_offset(HDR_SZ)
                    else:
                        self.calculate_offset(0)
            elif ((self.bin_verifier == "bl2") or(self.bin_verifier == "bl2_B")):
                if len(self.partitions.primary_partitions_verified_by_bl2) == 1:
                    self.calculate_offset(HDR_SZ)
                else:
                    self.calculate_offset(0)
            else:
                self.calculate_offset(0)

            self.check_68K_boundary()
            self.calculate_size()

    def post_parse_and_validate_partitions(self):
        for p in self.partitions:
            p.post_parse_and_validate_partitions()

    def parse_and_validate_static_and_load_addr(self):
        if (self.is_app_partition() == False):
            return

        virtual_1st_instruction_addr = phy2virtual(self.phy_code_offset)
        static_addr_int = self.flash_base_addr + virtual_1st_instruction_addr
        static_addr_hex = f'0x%08x' %(static_addr_int)
        self.static_addr = static_addr_hex
        # Set load_addr to a fixed value if it's different as static_addr
        self.load_addr = self.static_addr
        logging.debug(f'static_addr = {self.static_addr}, load address={self.load_addr}')

    def parse_and_validate_bin(self):
        if self.bin_name == None:
            self.bin_size = 0
            return

        if not os.path.exists(self.bin_name):
            logging.debug(f'bin {self.bin_name} for partition{self.idx} {self.partition_name} not exists')
            return

        self.bin_size = os.path.getsize(self.bin_name)
        if self.is_app_partition():
            if(self.vir_code_offset + self.bin_size > self.vir_partition_offset + self.vir_partition_size):
                logging.error(f'partition{self.idx} {self.partition_name} bin size %x > partition size %x' %(self.bin_size, self.vir_partition_size))
                exit(1)
        else:
            # TODO check data_bin size based on cbus and dbus
            self.bin_data_size = self.bin_size
            self.bin_total_size = self.bin_size

            if (self.bin_size > self.partition_size):
                logging.error(f'partition{self.idx} {self.partition_name} bin size %x > partition size %x' %(self.bin_size, self.partition_size))
                exit(1)

            if (self.bin_total_size > self.partition_size):
                logging.error(f'partition{self.idx} {self.partition_name} total bin size %x > partition size %x' %(self.bin_total_size, self.partition_size))
                exit(1)

    def parse_and_validate_after_build(self):
        self.parse_and_validate_bin()

    def __init__(self, partitions, idx, pdic, deduced_min_partition_offset):
        self.partitions = partitions
        self.bl1_secureboot_en = partitions.bl1_secureboot_en
        self.idx = idx
        self.ota_type = partitions.ota_type
        self.bl2_version = partitions.bl2_version
        self.tools_dir = partitions.tools_dir
        self.script_dir = partitions.script_dir
        self.pdic = pdic
        self.deduced_min_partition_offset = deduced_min_partition_offset
        self.flash_base_addr = partitions.flash_base_addr
        self.cpu_vector_align_bytes = partitions.cpu_vector_align_bytes
        self.need_add_crc = False
        self.bl2_exists = self.partitions.bl2_exists
        self.bl2_partition_idx = self.partitions.bl2_partition_idx
        self.Dbus_en = False
        self.partition_buf = bytearray()
        self.is_all_partition = False
        self.partition_hdr_pad_size = 0
        self.msp_pc = 0;
        
        self.parse_raw_fields()
        self.parse_and_validate_bin_type()
        self.parse_and_validate_partition_name()
        self.parse_and_validate_bin_name()
        self.parse_and_validate_verifier()
        self.parse_and_validate_partition_offset()
        self.parse_and_validate_partition_size()
        self.parse_and_validate_address()
        self.parse_and_validate_static_and_load_addr()
        self.parse_and_validate_partition_flags()

    def init_buf(self, buf, size, fill):
        for i in range(size):
            buf[i] = fill

    def is_1st_bin_verified_by_bl2(self):
        return self.partitions.is_1st_bin_verified_by_bl2(self.partition_name)

    def is_last_bin_verified_by_bl2(self):
        return self.partitions.is_last_bin_verified_by_bl2(self.partition_name)

    def add_magic_code(self, bin_file, aes_type):
        logging.debug(f'Add magic code BK7236 to {bin_file}')
        bk7236 = b'\x42\x4b\x37\x32\x33\x36\x00'
        with open(bin_file, 'r+b') as f:
            # if aes_type == 'RANDOM' or aes_type == 'FIXED':
            if aes_type == 'RANDOM':
                bl2_p = self.find_partition_by_name('bl2')
                bkaesrdm = b'\x42\x4b\x41\x45\x53\x52\x44\x4d' # BKAESRDM
                # release = b'\x52\x45\x4c\x45\x41\x53\x45\x2e' # RELEASE.
                forbid_start = struct.pack('<I', bl2_p.partition_offset);
                forbid_end = struct.pack('<I', bl2_p.partition_offset + bl2_p.partition_size)
                f.seek(0x40)
                f.write(bkaesrdm)
                f.write(forbid_start)
                f.write(forbid_end)
                f.write(self.msp_pc)
                # f.write(release)
            f.seek(0x100)
            f.write(bk7236)

    def add_version_code(self, bin_file):
        if (self.bl2_version == None):
            o = OTA('ota.csv')
            version = o.get_bootloader_version()
            logging.debug(f'get bl2 version from ota.csv:{version}')
        else:
            version = self.bl2_version
            logging.debug(f'get bl2 version from argument:{version}')
        numbers = [int(x) for x in version.split('.')]
        versions = bytes(numbers + [0] * (4-len(numbers)))
        logging.debug(f'Add version code {version} to {bin_file}')
        with open(bin_file, 'r+b') as f:
                f.seek(0x120)
                f.write(versions)

    def process_partition_app_aes_crc(self, aes_type, aes_key):
        if self.bin_name == None:
            return

        logging.debug(f'process app partition.{self.partition_name}')
        if self.is_all_partition:
            self.bin_name = f'{self.partition_name}_signed.bin'

        if (aes_type == 'RANDOM' and self.partition_name != 'bl2' and self.partition_name != 'bl2_B'):
            self.crc_bin_name = self.bin_name
            partition_hdr_pad_size = 0
        else:
            if aes_type == 'FIXED':
                self.aes_bin_name = f'{self.file_name_prefix}_aes.bin'
                aes_tool = get_flash_aes_tool()
                if self.is_all_partition:
                    start_address = hex(phy2virtual(self.phy_partition_offset))
                else:
                    start_address = hex(self.vir_code_offset)
                if os.path.exists(self.bin_name) == False:
                    logging.error(f'{self.bin_name} not exists, abort')
                    exit(1)
                logging.debug(f'encrypt {self.partition_name}, startaddress={start_address}, out={self.aes_bin_name}')
                cmd = f'{aes_tool} encrypt -infile {self.bin_name} -keywords {aes_key} -outfile {self.aes_bin_name} -startaddress {start_address}'
                run_cmd_not_check_ret(cmd)
                save_cmd(f'Encrypt partition {self.partition_name}:{self.bin_name}', cmd)
            else:
                self.aes_bin_name = self.bin_name

            if self.vir_code_offset == 0:
                self.add_magic_code(self.aes_bin_name, aes_type)
                self.add_version_code(self.aes_bin_name)

            if (aes_type == 'RANDOM' and self.partition_name == 'bl2'):
                self.crc_bin_name = self.aes_bin_name
            else:
                self.crc_bin_name = f'{self.file_name_prefix}_crc.bin'
                calc_crc16(self.aes_bin_name, self.crc_bin_name)
            partition_hdr_pad_size = self.partition_hdr_pad_size

            if self.is_xip() and self.is_primary:
                all_bin_pack = self.crc_bin_name
                with open(all_bin_pack,'rb+') as f:
                    xip_status_phy_offset = ceil_align((self.partition_offset + self.partition_size - 4096),34)
                    phy_bin_offset = xip_status_phy_offset - self.phy_partition_offset
                    f.seek(0, os.SEEK_END)  # set file pointer to the end of file.
                    end_pos = f.tell()      # get postion of end of file
                    offset = phy_bin_offset - end_pos
                    if offset < 0:
                        raise RuntimeError(f"file {self.file_name_prefix} don't have enough space.")
                    f.write(bytes([0xff]) * offset) # padding 0xff
                    f.write(b'\xEF\xBE\xAD\xDE')
                    f.seek(phy_bin_offset + 32)
                    f.write(b'\xEF\xBE\xAD\xDE')

        self.bin_size = os.path.getsize(self.crc_bin_name) + partition_hdr_pad_size
        logging.debug(f'{self.bin_name}: bin_size={self.bin_size}, pad_hdr_size={partition_hdr_pad_size} {self.partition_hdr_pad_size}')
        self.partition_buf = bytearray()
        with open(self.crc_bin_name, 'rb') as f:
            pad = bytes([0xFF]*partition_hdr_pad_size)
            self.partition_buf = pad
            self.partition_buf += f.read()

        save_bk_loader_cmd(self.partition_name, self.crc_bin_name, self.partition_offset + partition_hdr_pad_size)

    def process_partition_encrypted(self, key_partition, aes_type, aes_key):
        if self.is_encrypted() == False:
            return

        if self.bin_name == None:
            logging.error(f'encrypted partition {self.partition_name} not configure bin')
            exit(1)

        if os.path.exists(self.bin_name) == False:
            logging.error(f'encrypted partition {self.partition_name} {self.bin_name} not exists')
            exit(1)

        key_bin = f'{key_partition}.bin'
        if os.path.exists(key_bin) == False:
            logging.error(f'try encrypted partition {self.partition_name} but key.bin not exists')
            exit(1)

        nvs_tool = get_nvs_tool()

        if aes_type == 'FIXED':
            encrypted_bin_name = f'{self.partition_name}_aes.bin'
        else:
            encrypted_bin_name = f'{self.partition_name}.bin'
        cmd = f'{nvs_tool} nvs_key.bin {self.bin_name} {encrypted_bin_name} 0'
        run_cmd_not_check_ret(cmd)
        save_cmd(f"Encrypted partition {self.partition_name}:{self.bin_name}", cmd)

        self.partition_buf = bytearray()
        bin_size = os.path.getsize(encrypted_bin_name)
        partition_tail_pad_size = 0
        if self.partition_size > bin_size:
            partition_tail_pad_size = self.partition_size - bin_size

        with open(encrypted_bin_name, 'rb') as f:
            self.partition_buf += f.read()
            pad = bytes([0xFF]*partition_tail_pad_size)
            self.partition_buf += pad

        save_bk_loader_cmd(self.partition_name, encrypted_bin_name, self.partition_offset)

    def process_partition_nvs_key(self, aes_type, aes_key):
        if self.is_nvs_key() == False:
            return

        logging.debug(f'process nvs_key partition {self.partition_name}')
        key_bin_name = f'{self.partition_name}.bin'
        if os.path.exists(key_bin_name):
            logging.debug('{self.partition_name} using existing {key_in_name}')
        else:
            nvs_tool = f'{self.tools_dir}/NVS/nvs_partition_gen.py'
            cmd = f'{nvs_tool} generate-key --keyfile {key_bin_name}'
            run_cmd_not_check_ret(cmd)
            save_cmd(f'Generate NVS key {self.partition_name}:{key_bin_name}', cmd)
            shutil.copy(f'./keys/{key_bin_name}', f'./')

        if aes_type == 'RANDOM':
            self.crc_bin_name = self.bin_name
            partition_hdr_pad_size = 0
        else:
            if aes_type == 'FIXED':
                self.aes_bin_name = f'{self.file_name_prefix}_aes.bin'
                aes_tool = get_flash_aes_tool()
                self.phy_partition_offset = ceil_align(self.partition_offset, CRC_UNIT_TOTAL_SZ)
                start_address = hex(phy2virtual(self.phy_partition_offset))
                logging.debug(f'encrypt {self.partition_name}, startaddress={start_address}, out={self.aes_bin_name}')
                cmd = f'{aes_tool} encrypt -infile {key_bin_name} -keywords {aes_key} -outfile {self.aes_bin_name} -startaddress {start_address}'
                run_cmd_not_check_ret(cmd)
                save_cmd(f'Encrypt partition {self.partition_name}:{self.aes_bin_name}', cmd)
            else:
                self.aes_bin_name = self.bin_name

            self.crc_bin_name = f'{self.file_name_prefix}_crc.bin'
            calc_crc16(self.aes_bin_name, self.crc_bin_name)
            partition_hdr_pad_size = ceil_align(self.partition_offset, CRC_UNIT_TOTAL_SZ) - self.partition_offset

        self.partition_buf = bytearray()
        self.bin_size = os.path.getsize(self.crc_bin_name)
        with open(self.crc_bin_name, 'rb') as f:
            pad = bytes([0xFF]*partition_hdr_pad_size)
            self.partition_buf = pad
            if (self.bin_size + partition_hdr_pad_size) > self.partition_size:
                read_bin_size = self.partition_size - partition_hdr_pad_size
            else:
                read_bin_size = self.bin_size

            self.partition_buf += f.read(read_bin_size)
        logging.debug(f'{self.bin_name}: bin_size={self.bin_size}, read_bin_size = {read_bin_size}, hdr_pad_size={partition_hdr_pad_size}')
        save_bk_loader_cmd(self.partition_name, self.crc_bin_name, self.partition_offset + partition_hdr_pad_size)

    def process_partition_nvs(self, nvs_key_partition):
        if self.is_nvs() == False:
            return

        logging.debug(f'process nvs {self.partition_name}')
        nvs_bin_name = f'{self.partition_name}_aes.bin'
        if nvs_key_partition == None:
            logging.error(f'nvs key partition not exists')
            exit(1)

        if os.path.exists(nvs_bin_name):
            logging.debug('{self.partition_name} using existing {nvs_bin_name}')
        else:
            nvs_bin_csv = f'{self.partition_name}.csv'
            if os.path.exists(nvs_bin_csv) == False:
                logging.error(f'NVS {nvs_bin_csv} and {nvs_bin_name} not exists')
                exit(1)

            nvs_key_bin_name = f'{nvs_key_partition}.bin'
            nvs_tool = f'{self.tools_dir}/NVS/nvs_partition_gen.py'
            cmd = f'{nvs_tool} encrypt {nvs_bin_csv} {nvs_bin_name} {self.partition_size} --inputkey {nvs_key_bin_name}'
            logging.debug(f'create and encrypt {nvs_bin_name} from {nvs_bin_csv}: {cmd}')
            run_cmd_not_check_ret(cmd)
            save_cmd(f"Encrypts {self.partition_name}:{nvs_key_bin_name}", cmd)

            self.partition_buf = bytearray()
            with open(nvs_bin_name, 'rb') as f:
                self.partition_buf += f.read()

        save_bk_loader_cmd(self.partition_name, nvs_bin_name, self.partition_offset)

crc32_table = [0] * 256

class Partitions:
    def is_overwrite(self):
        return self.ota_type == 'OVERWRITE'

    def is_xip(self):
        return self.ota_type == 'XIP'

    def is_1st_bin_verified_by_bl2(self, partition_name):
        if (self.primary_all_partitions_cnt > 0) and (self.primary_partitions_verified_by_bl2[0] == partition_name):
            return True

        if (self.secondary_all_partitions_cnt > 0) and (self.secondary_partitions_verified_by_bl2[0] == partition_name):
            return True

        return False

    def is_last_bin_verified_by_bl2(self, partition_name):
        if (self.primary_all_partitions_cnt > 0) and (self.primary_partitions_verified_by_bl2[-1] == partition_name):
            return True

        if (self.secondary_all_partitions_cnt > 0) and (self.secondary_partitions_verified_by_bl2[-1] == partition_name):
            return True

        return False

    def find_partition_by_name(self, name):
        for p in self.partitions:
            if (name == p.partition_name):
                return p
        return None

    def create_normal_partitions(self):
        deduced_next_partition_offset = 0
        self.first_partition_offset = 0

        idx = -1
        for pdic in self.csv.dic_list:
            idx += 1
            p = Partition(self, idx, pdic, deduced_next_partition_offset)
            deduced_next_partition_offset = p.partition_offset + p.partition_size
            self.partitions.append(p)
            if (idx == 0):
                self.first_partition_offset = p.partition_offset

    def partition_name_to_idx(self, partition_name):
        idx = 0
        for p in self.partitions:
            if (partition_name == p.partition_name):
                return idx
            idx += 1
        return -1

    def create_all_partition(self, partition_name, child_partition_names):
        child_num = len(child_partition_names)
        if (child_num <= 0):
            return

        partition_name_1st = child_partition_names[0]
        partition_1st = self.find_partition_by_name(partition_name_1st)

        code_pad_size = partition_1st.vir_code_offset - partition_1st.vir_partition_offset

        partition_name_last = child_partition_names[-1]
        partition_last = self.find_partition_by_name(partition_name_last)

        all_partition = copy.copy(partition_1st)

        child_partition_num = len(child_partition_names)

        all_partition.bin_size = 0
        all_partition.partition_name = partition_name
        all_partition.file_name_prefix = partition_name
        all_partition.partition_size = (partition_last.partition_offset - partition_1st.partition_offset) + partition_last.partition_size

        all_partition.Dbus_en = True
        all_partition.is_all_partition = True

        if (partition_name == 'primary_all'):
            all_partition.partition_hdr_pad_size = partition_1st.phy_partition_offset - partition_1st.partition_offset
            all_partition.partition_tail_pad_size = (all_partition.partition_offset+all_partition.partition_size) - floor_align(all_partition.partition_offset+all_partition.partition_size,34)

            all_partition.phy_partition_size = all_partition.partition_size-all_partition.partition_hdr_pad_size-all_partition.partition_tail_pad_size
            all_partition.vir_partition_size = floor_align(phy2virtual(all_partition.phy_partition_size), 4096)

            all_partition.vir_sign_size = all_partition.vir_partition_size
            all_partition.vir_code_size = all_partition.vir_sign_size - code_pad_size - HDR_SZ
            all_partition.phy_code_size = virtual2phy(all_partition.vir_code_size)
        else:
            partition_primary = self.find_partition_by_name('primary_all')
            all_partition.phy_code_size = partition_primary.phy_code_size
            all_partition.vir_code_size = partition_primary.vir_code_size

        idx = self.partition_name_to_idx(partition_name_last)
        self.partitions.insert(idx + 1, all_partition)
        logging.debug(f'create virtual partition: {partition_name} id={idx}')
        logging.debug(f'create virtual partition: offset={all_partition.partition_offset}, size={all_partition.partition_size}')
        logging.debug(f'create virtual partition: vir_partition_size={all_partition.vir_partition_size}, virtual_code_size={all_partition.vir_code_size}')

    def create_all_partitions(self):
        self.create_all_partition('primary_all', self.primary_partitions_verified_by_bl2)
        self.create_all_partition('secondary_all', self.secondary_partitions_verified_by_bl2)

    def process_partition_partition(self):
        partition = self.find_partition_by_name("partition")
        if partition == None:
            logging.debug(f'partition partition not exists, not create partition.bin')
            return

        if os.path.exists('ppc_config.bin'):
            logging.debug(f'copy ppc_config.bin to partition_raw.bin')
            with open('partition_raw.bin','wb') as f,open('ppc_config.bin','rb') as f_src:
                f.write(f_src.read())
            pad_len = 0
        else:
            pad_len = 1024

        with open("partition_raw.bin", 'a+b') as f:
            if pad_len > 0:
                f.write(bytes([0xFF]*pad_len))

            for p in self.partitions:
                name = p.partition_name.encode('utf-8')
                if len(name) < 20:
                    name += bytes([0xFF] * (20 - len(name)))
                f.write(name)
                
                partition_type = PartitionType.PARTITION_TYPE_ANY
                if p.partition_type == 'app':
                    partition_type = PartitionType.PARTITION_TYPE_APP
                elif p.partition_type == 'data':
                    partition_type = PartitionType.PARTITION_TYPE_DATA
                else:
                    partition_type = PartitionType.PARTITION_TYPE_ANY

                type = struct.pack(">B",(partition_type.value))
                f.write(type)

                partition_subtype = PartitionSubType.PARTITION_SubType_BK_UNDEFINED_0

                subtype = struct.pack(">B",(partition_subtype.value))
                f.write(subtype)

                offset = struct.pack(">I",(p.partition_offset))
                f.write(offset)
    
                size = struct.pack(">I",(p.partition_size))
                f.write(size)

                flags = struct.pack(">H",(p.partition_flags))
                f.write(flags)

        with open('partition.bin','wb+') as f,open('partition_raw.bin','rb') as f_src:
                f.write(f_src.read())
 
        partition.bin_name = 'partition.bin'
        partition.bin_size = os.path.getsize(partition.bin_name)

        partition.partition_buf = bytearray()
        with open(partition.bin_name, 'rb') as f:
            partition.partition_buf += f.read()

        save_bk_loader_cmd(partition.partition_name, partition.bin_name, partition.partition_offset)

    def check_partition_illegal(self):
        if(self.is_overwrite()):
            for p in self.partitions:
                if(p.partition_name.find("secondary") != -1):
                    logging.error("overwrite cannot have secondary partitions!")
                    exit(1)
            p = self.find_partition_by_name("ota")
            primary_all = self.find_partition_by_name("primary_all")
            if(primary_all and primary_all.partition_size % (4096) != 0):
                logging.error("total size of all primary partition should be 4k aligned!")
        elif(self.is_xip()):
            logging.debug("TODO")
        else:
            logging.debug("No OTA")

    def create_partitions(self):
        self.create_normal_partitions()
        self.create_all_partitions()

    def append_ota_partitions(self, partition_name):
        self.ota_partitions.append(partition_name)
        logging.debug(f'ota partitions: {self.ota_partitions}')

    def append_primary_partitions_verified_by_bl2(self, partition_name):
        self.primary_partitions_verified_by_bl2.append(partition_name)
        self.primary_all_partitions_cnt = len(self.primary_partitions_verified_by_bl2)
        logging.debug(f'primary partitions verified by bl2:')
        logging.debug(f'{self.primary_partitions_verified_by_bl2}')

    def append_secondary_partitions_verified_by_bl2(self, partition_name):
        self.secondary_partitions_verified_by_bl2.append(partition_name)
        self.secondary_all_partitions_cnt = len(self.secondary_partitions_verified_by_bl2)
        logging.debug(f'secondary partitions verified by bl2:')
        logging.debug(f'{self.secondary_partitions_verified_by_bl2}')

    def parse_and_validate_tfm_ns(self):
        self.tfm_ns_exists = False
        self.primary_cpu0_app_exists = False
        self.ota_exists = False

        if 'primary_tfm_ns' in self.partition_names:
            self.tfm_ns_exists = True

        if 'primary_cpu0_app' in self.partition_names:
            self.primary_cpu0_app_exists = True

        if 'ota' in self.partition_names:
            self.ota_exists = True

        logging.debug(f'tfm_ns exists={self.tfm_ns_exists}, primary_cpu0_app={self.primary_cpu0_app_exists}')

    def parse_and_validate_tfm_s(self):
        if self.tfm_exists:
            if ('sys_ps' not in self.partition_names) or ('sys_its' not in self.partition_names):
                logging.error(f'TFM need partition "sys_ps", "sys_its"')
                exit(1)

    def parse_and_validate_cpu0_app(self):
        if self.primary_cpu0_app_exists:
            if ('sys_net' not in self.partition_names):
                logging.error(f'partition primary_cpu0_app need partition "sys_net"')
                exit(1)
        # if self.ota_exists:
        #     if ('ota_control' not in self.partition_names):
        #         logging.error(f'partition ota need partition "ota_control"')
        #         exit(1)

    def parse_and_validate_secureboot_partitions(self):
        logging.debug(f'secure is {self.bl1_secureboot_en}')
        if self.bl1_secureboot_en:
            if len(self.partition_names) < 2:
               logging.error(f'secureboot should contains "bl1_control", "primary_manifest"')
               exit(1)

            if (not ('bl1_control' in self.partition_names)) or (not ('primary_manifest' in self.partition_names)):
               logging.error(f'secureboot missing "bl1_control" or "primary_manifest" or "secondary_manifest"')
               exit(1)

    def check_duplicated_partitions(self):
        if (len(self.partition_names) != len(set(self.partition_names))):
            logging.error(f'{self.partition_csv} contains duplicated partitions!')
            exit(1)

    def parse_and_validate_partitions_before_create(self):
        logging.debug(f'before create validation')
        partitions_cnt = len(self.partition_names)
        if (partitions_cnt == 0):
            logging.error(f'{self.partition_csv} has no partition')
            exit(1)
        self.check_duplicated_partitions()
        self.parse_and_validate_secureboot_partitions()
        self.parse_and_validate_tfm_ns()
        self.parse_and_validate_tfm_s()
        self.parse_and_validate_cpu0_app()

    def parse_and_validate_partitions_after_create(self):
        logging.debug(f'after create validation')
        logging.debug(f'primary/secondary continously')
        logging.debug(f'primary/secondary in-order')
        logging.debug(f'at least one X partition for bl2')
        logging.debug(f'other partitions checking')

    def parse_and_validate_partitions_after_build(self):
        logging.debug(f'after build validation')
        for p in self.partitions:
            p.parse_and_validate_after_build()

    def init_globals(self):

        for p in self.csv.dic_list:
            self.partition_names.append(p['Name'])

        self.tfm_exists = False
        if 'primary_tfm_s' in self.partition_names:
            self.tfm_exists = True

        self.bl2_exists = False
        self.bl2_partition_idx = -1
        self.bl2_B_partition_idx = -1
        if 'bl2' in self.partition_names:
            self.bl2_exists = True
            self.bl2_partition_idx = self.partition_names.index('bl2')

        if 'bl2_B' in self.partition_names:
            self.bl2_exists = True
            self.bl2_partition_idx = self.partition_names.index('bl2_B')

        self.bootloader_exists = False
        if 'primary_bootloader' in self.partition_names:
            self.bootloader_exists = True

        logging.debug(f'bl1_secureboot_en={self.bl1_secureboot_en}, tfm_exists={self.tfm_exists}, bl2_exits={self.bl2_exists}, bl2_index={self.bl2_partition_idx}')
 
    def init_globals_default(self):
        self.partitions = []
        self.partition_names = []

        self.flash_base_addr = 0x02000000
        self.flash_size = 0x400000
        self.cpu_vector_align_bytes = 512
        self.need_crc = True
        self.primary_partitions_verified_by_bl2 = []
        self.secondary_partitions_verified_by_bl2 = []
        self.all_app_pack_idx_list = []
        self.ota_partitions = []

        script_dir = get_script_dir()
        self.script_dir = script_dir
        self.tools_dir = f'{script_dir}/../tools'

    def dump_partitions(self):
        logging.debug(f'dump {self.partition_csv}')
        with open(self.partition_csv, 'r') as f:
            rows = csv.reader(f)
            for row in rows:
                logging.debug(f'{row}')

    def process_bl2_with_jump_bin(self, bl2_bin_name):
        jump_data = None
        bl2_new_data = None
        bl2_B_new_data = None
        jump_bin_location_pos = 0xB4
        jump_bin_size_pos = 0xB8
        jump_size = 256 #os.path.getsize('jump.bin')  #need check
        bl2_bin_size = os.path.getsize(bl2_bin_name)
 
        if self.bl1_secureboot_en == False:
            return

        partition_input_name = bl2_bin_name.replace(".bin","")
        bl2_p = self.find_partition_by_name(partition_input_name)

        logging.debug(f'bl2_bin_name {bl2_bin_name}, bl2_bin_ori_size :{bl2_bin_size}, bl2_bin_fin_size:{bl2_bin_size+jump_size},bl2_partition_vir_size :{((bl2_p.partition_size // 34) * 32)}')

        if((jump_size + bl2_bin_size) > ((bl2_p.partition_size // 34) * 32)):
            logging.error(f'bl2.bin  or bl2_B.bin size is overflow!!!!!!!!!!')
            exit(1)

        with open('jump.bin', 'rb') as jump_f:
            jump_data = jump_f.read()

        with open(bl2_bin_name, 'rb') as bl2_f1:
            input_bak_name = partition_input_name + "_bak.bin"
            with open(input_bak_name, 'wb') as bl2_bak:
                bl2_bak.write(bl2_f1.read())

        with open(bl2_bin_name, 'rb+') as bl2_f2:
            bl2_f2.seek(jump_bin_location_pos) #0xB4
            bl2_f2.write((struct.pack('I', bl2_bin_size) + struct.pack('I', jump_size)))

        with open(bl2_bin_name, 'rb') as bl2_f3:
            bl2_data = bl2_f3.read()
            bl2_new_data = bl2_data[:bl2_bin_size] + jump_data + bl2_data[bl2_bin_size:]
            with open(bl2_bin_name, 'rb+') as bl2_f4:
                bl2_f4.write(bl2_new_data)

    def add_jump_bin_to_bl2(self):
        if self.boot_ota == True:
            bl2_p = self.find_partition_by_name('bl2')
            if bl2_p == None :
                return
            self.process_bl2_with_jump_bin(bl2_p.bin_name)
            bl2_B_p = self.find_partition_by_name('bl2_B')
            if bl2_B_p == None :
                return
            self.process_bl2_with_jump_bin(bl2_B_p.bin_name)


    def __init__(self, partition_csv, ota_type, boot_ota, bl1_secureboot_en, bl2_version=None):
        self.bl1_secureboot_en = bl1_secureboot_en
        self.partition_csv = partition_csv
        self.ota_type = ota_type
        self.boot_ota = boot_ota
        self.bl2_version = bl2_version

        self.secondary_all_partitions_cnt = 0
        self.csv = Csv(partition_csv, True, partition_keys_v2, partition_keys_v1)
        self.dump_partitions()
        self.init_globals_default()
        self.init_globals()
        self.parse_and_validate_partitions_before_create()
        self.create_partitions()
        self.parse_and_validate_partitions_after_create()
        self.add_jump_bin_to_bl2()

    def gen_bin_for_bl2_signing(self, partition_name, child_partition_names, app_version):
        length = len(child_partition_names)
        if (length <= 0):
            logging.debug(f'Skip generate partition {partition_name}')
            return

        logging.debug(f'Generate {partition_name}, child partitions: {child_partition_names}')
        all_bin_name = f'{partition_name}.bin'
        parts = app_version.split('.')
        iv_major = struct.pack('B', int(parts[0]))
        iv_minor = struct.pack('B', int(parts[1]))
        iv_revision = struct.pack('<H', int(parts[2]))
        chip = struct.pack('<6s','BK7236'.encode('utf-8'))
        with open(all_bin_name, 'wb+') as f:
            idx = -1
            for pname in child_partition_names:
                p = self.find_partition_by_name(pname)
                idx += 1
                if idx == 0:
                    pad_size = p.vir_code_offset - p.vir_partition_offset - HDR_SZ
                    start_offset = p.vir_code_offset - pad_size
                else:
                    pad_size = p.vir_code_offset - start_offset -f.tell()

                logging.debug(f'pad_size:{hex(pad_size)}')
                pad = bytes([0xFF]*(pad_size))
                f.write(pad)
                with open(p.bin_name, 'rb') as pf:
                    f.write(pf.read())
            f.write(iv_major)
            f.write(iv_minor)
            f.write(iv_revision)
            f.write(chip)
        shutil.copy(all_bin_name, 'app.bin')

    def process_bl1_control(self, boot_ota):
        if self.bl1_secureboot_en == False:
            return

        p = self.find_partition_by_name('bl1_control')
        p.bin_name = 'bl1_control.bin'
        with open(p.bin_name, 'wb') as f:
            logging.debug(f'create new {p.bin_name}')
            pad = bytes([0xFF]*(0xF00))
            f.write(pad)

        if self.aes_type == 'RANDOM':
            logging.debug(f'Copy jump_bin to {p.bin_name}')
            with open(p.bin_name, 'rb+') as bl1_control_f:
                with open("jump.bin", 'rb') as jump_f:
                    p.msp_pc = jump_f.read(8)
                    jump_f.seek(0)
                    jump_data = jump_f.read()
                    bl1_control_f.write(jump_data)
                logging.debug(f'Copy MSP and PC from provision.bin to {p.bin_name}')
                privison_msp_pc = bytearray()
                with open('provision.bin', 'rb') as f:
                    privison_msp_pc = f.read(8)
                    bl1_control_f.seek(0)
                    bl1_control_f.write(privison_msp_pc)
            aes_bin_name = p.bin_name
        else:
            if boot_ota == False:
                logging.debug(f'Copy MSP and PC from bl2.bin to {p.bin_name}')
                bl2_msp_pc = bytearray()
                with open('bl2.bin', 'rb') as f:
                    bl2_msp_pc = f.read(64)
                    with open(p.bin_name, 'rb+') as bl1_control_f:
                        bl1_control_f.seek(0)
                        bl1_control_f.write(bl2_msp_pc)
            else:
                if os.path.exists("bl2_B.bin"):
                    logging.debug(f'Copy jump_bin to {p.bin_name}')
                    with open("jump.bin", 'rb') as jump_f:
                        jump_data = jump_f.read()
                        with open(p.bin_name, 'rb+') as bl1_control_f:
                            bl1_control_f.write(jump_data)

            if self.aes_type == 'FIXED':
                aes_bin_name = f'{p.partition_name}_aes.bin'
                aes_tool = get_flash_aes_tool()
                start_address = hex(phy2virtual(p.partition_offset))
                cmd = f'{aes_tool} encrypt -infile {p.bin_name} -keywords {self.aes_key} -outfile {aes_bin_name} -startaddress {start_address}'
                run_cmd_not_check_ret(cmd)
            else:
                aes_bin_name = p.bin_name

        p.add_magic_code(aes_bin_name, self.aes_type)
        crc_bin_name = f'{p.partition_name}_crc.bin'
        calc_crc16(aes_bin_name, crc_bin_name)


        read_size = os.path.getsize(crc_bin_name)
        if read_size > p.partition_size:
            read_size = p.partition_size

        with open(crc_bin_name, 'rb') as f:
            p.partition_buf = f.read(read_size)

    def process_boot_flag(self):  #need optimize
        if self.bl1_secureboot_en == False:
            return

        p = self.find_partition_by_name('boot_flag')
        if p == None :
            return

        boot_flag_val = bytes([0x63,0x54,0x72,0x4c,0x1])
        p.bin_name = 'boot_flag.bin'
        with open(p.bin_name, 'wb+') as f:
            logging.debug(f'create new {p.bin_name}')
            pad = bytes([0x0]*(0x20))
            f.write(pad)
            f.seek(32)
            pad = bytes([0xFF]*(0xFE0))
            f.write(pad)

        with open(p.bin_name, 'rb+') as f:
            f.seek(0)
            f.write(boot_flag_val)
            if self.aes_type == 'RANDOM':
                with open("jump.bin", 'rb') as jump_f:
                    jump_data = jump_f.read(8)
                    f.seek(8)
                    f.write(jump_data)

        with open(p.bin_name, 'rb') as f:
            p.partition_buf = f.read()

    def process_manifest(self):
        p = self.find_partition_by_name('primary_manifest')
        if p == None:
            return

        with open(p.bin_name, 'rb') as f:
            p.partition_buf = f.read()

        p2 = self.find_partition_by_name('secondary_manifest')
        if p2 == None:
            return

        with open(p2.bin_name, 'rb') as f:
            p2.partition_buf = f.read()

    def process_app_aes_crc(self):
        logging.debug('process app partition, add aes and crc')
        for p in self.partitions:
            if (p.partition_name == 'bl2') or (p.partition_name == 'bl2_B')or (p.partition_name == 'primary_all'):
                p.process_partition_app_aes_crc(self.aes_type, self.aes_key)

    def process_encrypted(self):
        logging.debug('process encrypted partition')
        for p in self.partitions:
            if self.is_partition_need_pack(p) == False:
                logging.debug(f'process_encrypted: skip {p.partition_name}, no need pack')
                continue

            p.process_partition_encrypted(self.nvs_key_partition, self.aes_type, self.aes_key)

    def process_nvs(self):
        nvs_key_partition_cnt = 0
        self.nvs_key_partition = None
        logging.debug(f'process nvs partitions')
        for p in self.partitions:
            if p.is_nvs_key():
                if nvs_key_partition_cnt == 1:
                    logging.debug(f'More than 2 partition with nvs_key subtype')
                    exit(1)

                if self.is_partition_need_pack(p) == False:
                    logging.debug(f'process_nvs_key: skip {p.partition_name}, no need pack')
                    continue

                self.nvs_key_partition = p.partition_name
                nvs_key_partition_cnt = nvs_key_partition_cnt + 1
                p.process_partition_nvs_key(self.aes_type, self.aes_key)

        for p in self.partitions:
            if self.is_partition_need_pack(p) == False:
                logging.debug(f'process_nvs: skip {p.partition_name}, no need pack')
                continue
            p.process_partition_nvs(self.nvs_key_partition)

    def gen_bins_for_bl2_signing(self, app_version):
        self.gen_bin_for_bl2_signing('primary_all', self.primary_partitions_verified_by_bl2, app_version)
        self.gen_bin_for_bl2_signing('secondary_all', self.secondary_partitions_verified_by_bl2, app_version)

    def gen_all_app_global_hdr(self, img_num, img_hdr_list, version, magic_val):
        if self.bl1_secureboot_en == False:
            magic = "BL1DLV10".encode()
        else:
            magic = magic_val.encode()
        magic = struct.pack('8s', magic)
        version = struct.pack('>I', version)
        hdr_len = struct.pack('>H', GLOBAL_HDR_LEN)
        img_num = struct.pack('>H', img_num)
        flags = struct.pack('>I', 0)
        reserved1 = struct.pack('>I', 0)
        reserved2 = struct.pack('>I', 0)
        global_crc_content = version + hdr_len + img_num + flags + reserved1 + reserved2
        for img_hdr in img_hdr_list:
            global_crc_content += img_hdr

        self.init_crc32_table()
        global_crc = self.crc32(0xffffffff, global_crc_content)
        global_crc = struct.pack('>I', global_crc)
        all_app_global_hdr = magic + global_crc + version + hdr_len + img_num + flags + reserved1 + reserved2
        logging.debug(f'add download global hdr: magic={magic}, img_num={img_num}, version={version}, flags={flags}, crc={global_crc}')
        return all_app_global_hdr

    def convert_to_bigendian(self, offset, size, start_addr, img_offset, img_len, checksum, version, type, reserved):
        partition_offset = struct.pack('>I', offset)
        partition_size = struct.pack('>I', size)
        flash_start_addr = struct.pack('>I', start_addr)
        img_offset = struct.pack('>I', img_offset)
        img_len = struct.pack('>I', img_len)
        checksum = struct.pack('>I', checksum)
        version = struct.pack('>I', version)
        type = struct.pack('>H', type)
        reserved = struct.pack('>H', reserved)
        hdr = partition_offset + partition_size + flash_start_addr + img_offset + img_len  + checksum + version + type + reserved
        return hdr

    def gen_sub_img_hdr(self, partition, img_offset, version=0, type=0):
        logging.debug(f'add download img hdr of {partition.partition_name}: partition_size=%x, img_offset=%x, version=%x, type=%x'
                       %(partition.partition_size, img_offset, version ,type))
        img_len = len(partition.partition_buf)
        self.init_crc32_table()
        checksum = self.crc32(0xffffffff,partition.partition_buf)
 
        return self.convert_to_bigendian(partition.partition_offset, partition.partition_size, partition.partition_offset, img_offset, 
                                         img_len, checksum, version, type, 0) 

    def gen_merged_all_bin(self, bin_name, partition_idx_list, type_list):
        logging.debug(f'pack {bin_name} idx_list: {partition_idx_list}, type_list:{type_list}')
        img_num = len(partition_idx_list)
        if (img_num == 0):
            return

        if self.sigle_bin == True:
            if self.aes_type == 'RANDOM':
                bootloader_bin = 'provision_pack.bin'
                if not os.path.exists(bootloader_bin):
                    logging.error(f'{bootloader_bin}')
                    exit(1)
                img_num += 1
                if self.pk_hash == True:
                    otp_efuse_config_json = "otp_efuse_config.json"
                    if  not os.path.exists(otp_efuse_config_json):
                        logging.error(f'{otp_efuse_config_json} not exists')
                        exit(1)
                    img_num += 1

            else:
                bootloader_bin = 'bootloader.bin'
                if not os.path.exists(bootloader_bin):
                    logging.error(f'{bootloader_bin} not exists')
                    exit(1)
                img_num += 1

        pack_file_name = bin_name
        offset = (IMG_HDR_LEN * img_num) + GLOBAL_HDR_LEN
        logging.debug(f'pack {bin_name}: img num={img_num}, total header len=%x' %(offset))

        img_hdr_list = []

        if self.sigle_bin == True:
            if self.aes_type == 'RANDOM':
                if self.pk_hash == True:
                    fields_to_decrypt = ['bl1_rotpk_hash', 'bl2_rotpk_hash']
                    with open(otp_efuse_config_json, 'r') as json_file:
                        json_content = json_file.read()
                        json_content = re.sub(r'#.*', '', json_content)
                        data = json.loads(json_content)
                    rotpk_hash = bytearray()
                    size = 0
                    for item in data.get("Security_Data", []):
                        name = item.get("name")
                        if name in fields_to_decrypt:
                            if name == 'bl1_rotpk_hash':
                                otp_start_addr_hex = item["start_addr"]
                                otp_start_addr = int(otp_start_addr_hex, 16)
                            rotpk_data_hex = item["data"]
                            rotpk_data = bytes.fromhex(rotpk_data_hex)
                            rotpk_hash.extend(rotpk_data)

                    img_hdr = self.convert_to_bigendian(otp_start_addr, len(rotpk_hash), otp_start_addr, offset, len(rotpk_hash), 0x0, 0x0, 0x0, 0x1)
                    offset += len(rotpk_hash)
                    img_hdr_list.append(img_hdr)

            size = os.path.getsize(bootloader_bin)
            img_hdr = self.convert_to_bigendian(0x0, size, 0x0, offset, size, 0x0, 0x0, 0x0, 0x0)
            offset += size
            img_hdr_list.append(img_hdr)

        i = -1
        for idx in partition_idx_list:
            partition = self.partitions[idx]
            i += 1
            img_hdr = self.gen_sub_img_hdr(partition, img_offset=offset, version=0, type=type_list[i])
            offset = offset + len(partition.partition_buf)
            img_hdr_list.append(img_hdr)

        if bin_name == 'all-app.bin':
            if self.sigle_bin == True:
                if self.aes_type == 'RANDOM':
                    any_app_global_hdr = self.gen_all_app_global_hdr(img_num=img_num, img_hdr_list=img_hdr_list, version=1, magic_val="BLXDLV10")
                else:
                    any_app_global_hdr = self.gen_all_app_global_hdr(img_num=img_num, img_hdr_list=img_hdr_list, version=1, magic_val="BL1DLV10")  
            else:
                any_app_global_hdr = self.gen_all_app_global_hdr(img_num=img_num, img_hdr_list=img_hdr_list, version=1, magic_val="BKDLV10.")
        else:
            any_app_global_hdr = self.gen_all_app_global_hdr(img_num=img_num, img_hdr_list=img_hdr_list, version=1, magic_val="BL2DLV10")

        offset = 0
        with open(pack_file_name, 'wb+') as f:
            f.seek(offset)
            f.write(any_app_global_hdr)
            offset += GLOBAL_HDR_LEN

            for img_hdr in img_hdr_list:
                f.seek(offset)
                f.write(img_hdr)
                offset += IMG_HDR_LEN

            if self.sigle_bin == True:
                if self.aes_type == 'RANDOM':
                    f.seek(offset)
                    if self.pk_hash == True:
                        f.write(rotpk_hash)
                        offset += len(rotpk_hash)
                with open(bootloader_bin, 'rb') as pro_f:
                    f.write(pro_f.read())
                    offset += os.path.getsize(bootloader_bin)
            for idx in partition_idx_list:
                partition = self.partitions[idx]
                f.seek(offset)
                f.write(partition.partition_buf)

                logging.debug(f'pack {bin_name}: partitions{idx}.{partition.partition_name}: offset=%x, partition_size=%x, bin_size=%x, bin_tail_size=%x'
                    %(offset, partition.partition_size, len(partition.partition_buf), partition.bin_tail_size))
                offset += len(partition.partition_buf)

    def gen_merged_partitions_bin(self, bin_name, partition_idx_list):
        logging.debug(f'pack {bin_name} idx_list: {partition_idx_list}')
        f = open(bin_name, 'wb+')
        first_partition = self.partitions[partition_idx_list[0]]
        first_partition_offset = first_partition.partition_offset
        for idx in partition_idx_list:
            p = self.partitions[idx]
            if len(p.partition_buf) == 0:
                logging.debug(f'{p.partition_name} partition_buf is empty!')
                exit(1)

            if p.is_app_partition():
                pad_size = p.phy_code_offset - first_partition_offset - f.tell()
            else:
                pad_size = p.partition_offset - first_partition_offset - f.tell()
            logging.debug(f'merge {bin_name}: {p.partition_name} seek={hex(p.partition_offset)} len={hex(len(p.partition_buf))} pad_size={pad_size}')
            pad = bytes([0xFF]*(pad_size))
            f.write(pad)
            f.write(p.partition_buf)

        if (bin_name == 'provision_pack.bin'):
            append_bin = 'provision.bin'
            if not os.path.exists(append_bin):
                logging.error(f'{append_bin} not exists')
                exit(1)
            pad_size = 0x22000 - first_partition_offset - f.tell()
            pad = bytes([0xFF]*(pad_size))
            f.write(pad)
            with open(append_bin, 'rb') as af:
                content = af.read()
                f.write(content)

            append_bin = 'bl2_B.bin'
            if not os.path.exists(append_bin):
                logging.error(f'{append_bin} not exists')
                exit(1)
            pad_size = 0x33000 - first_partition_offset - f.tell()
            pad = bytes([0xFF]*(pad_size))
            f.write(pad)
            with open(append_bin, 'rb') as af:
                content = af.read()
                f.write(content)

        if bin_name == 'bootloader_B.bin':
            boot_B_bin_name = 'bootloader_B.bin'
            boot_flag_val = bytearray([2])
            with open(boot_B_bin_name, 'rb') as b_flag_f:
                data = b_flag_f.read()

            position = (self.find_partition_by_name('boot_flag').partition_offset + 4)
            logging.debug(f'position  {position}, boot_flag_val {boot_flag_val}')
            data = data[:position] + boot_flag_val + data[position+1:]
            with open(boot_B_bin_name, 'wb') as b_flag_f1:
                b_flag_f1.write(data)

        f.flush()
        f.close()

    def gen_provisioning_bin(self):
        idx_list = self.get_pack_idx_list('bootloader.bin')
        self.gen_merged_partitions_bin('bootloader.bin', idx_list)
        if (self.boot_ota == True):
            idx_list = self.get_pack_idx_list('bootloader_B.bin')
            logging.debug(f'********************* bootloader_B idx_list {idx_list}')
            self.gen_merged_partitions_bin('bootloader_B.bin', idx_list)
        if self.aes_type == 'RANDOM':
            self.gen_merged_partitions_bin('provision_pack.bin', idx_list)

    def gen_all_apps_bin(self):
        pack_bin = 'all-app.bin'
        idx_list = self.get_pack_idx_list(pack_bin)
        if self.aes_type == 'RANDOM':
            type_list = []
            for idx in idx_list:
                p = self.partitions[idx]
                if (p.is_app_partition()):
                    type_list.append(1)
                else:
                    type_list.append(0)
            self.gen_merged_all_bin(pack_bin, idx_list, type_list)
        else:
            self.gen_merged_all_bin(pack_bin, idx_list, [0]*len(idx_list))

    def gen_bootloader_ota_bin(self):
        if self.boot_ota  == False:
            return

        pack_bin = 'bootloader_ota.bin'
        idx_list = self.get_pack_idx_list(pack_bin)
        if self.bl1_secureboot_en == True:
            if self.aes_type == 'RANDOM':
                type_list = []
                for idx in idx_list:
                    p = self.partitions[idx]
                    if (p.is_app_partition()):
                        type_list.append(1)
                    else:
                        type_list.append(0)
                self.gen_merged_all_bin(pack_bin, idx_list, type_list)
            else:
                self.gen_merged_all_bin(pack_bin, idx_list, [0]*len(idx_list))
        else:
            self.gen_merged_partitions_bin(pack_bin, idx_list)


    def make_crc32_table(self):
        global crc32_table
        if crc32_table[255] != 0:
            return
        
        for i in range(256):
            c = i
            for bit in range(8):
                if c & 1:
                    c = (c >> 1) ^ 0xEDB88320
                else:
                    c = c >> 1
            crc32_table[i] = c

    def crc32_ver2(self,crc, buf):
        self.make_crc32_table()
        for byte in buf:
            crc = (crc >> 8) ^ crc32_table[(crc ^ byte) & 0xFF]
        return crc



    def init_crc32_table(self):
        self.make_crc32_table()

    def crc32(self, crc, buf):
        for byte in buf:
            crc = (crc >> 8) ^ crc32_table[(crc ^ byte) & 0xFF]
        return crc

    def gen_ota_global_hdr(self, img_num, img_hdr_list, global_security_counter):
        magic = "BK723658".encode()
        magic = struct.pack('8s', magic)
        global_security_counter = struct.pack('<I', global_security_counter)
        hdr_len = struct.pack('<H', GLOBAL_HDR_LEN)
        img_num = struct.pack('<H', img_num)
        flags = struct.pack('<I', 0)
        reserved1 = struct.pack('<I', 0)
        reserved2 = struct.pack('<I', 0)
        global_crc_content = global_security_counter + hdr_len + img_num + flags + reserved1 + reserved2
        for img_hdr in img_hdr_list:
            global_crc_content += img_hdr

        self.init_crc32_table()
        global_crc = self.crc32(0xffffffff, global_crc_content)
        global_crc = struct.pack('<I', global_crc)
        ota_global_hdr = magic + global_crc + global_security_counter + hdr_len + img_num + flags + reserved1 + reserved2
        logging.debug(f'add OTA global hdr: magic={magic}, img_num={img_num}, security_counter={global_security_counter}, flags={flags}, crc={global_crc}')
        return ota_global_hdr

    def gen_ota_img_hdr(self, partition_name, img_offset, flash_offset, img_content, security_counter, img_flags):
        logging.debug(f'add ota img hdr of {partition_name}: img_offset=%x, flash_offset=%x, security_counter=%x, img_flags=%x'
            %(img_offset, flash_offset, security_counter, img_flags))
        img_offset = struct.pack('<I', img_offset)
        flash_offset = struct.pack('<I', flash_offset)
        security_counter = struct.pack('<I', security_counter)

        img_len = len(img_content)
        img_len = struct.pack('<I', img_len)

        self.init_crc32_table()
        checksum = self.crc32(0xffffffff,img_content)
        checksum = struct.pack('<I', checksum)
        flags = 0
        flags = struct.pack('<I', img_flags)
        reserved1 = 0
        reserved1 = struct.pack('<I', reserved1)
        reserved2 = 0
        reserved2 = struct.pack('<I', reserved2)
        hdr = img_len + img_offset + flash_offset + checksum + security_counter + flags + reserved1 + reserved2
        return hdr 

    def add_ota_hdr(self, ota_partition_name, ota_sign_bin, ota_bin, sc):
        ota_partition = self.find_partition_by_name(ota_partition_name)
        img_num = 1
        img_hdr_list = []
        with open(ota_sign_bin,'rb+') as src,open(ota_bin,'w+b') as dst:
            offset = (IMG_HDR_LEN * img_num) + GLOBAL_HDR_LEN
            dst.seek(offset)
            img_content = src.read()
            dst.write(img_content)

            img_hdr = self.gen_ota_img_hdr( ota_partition.partition_name, img_offset = 0, 
                                                    flash_offset=ota_partition.partition_offset,
                                                    img_content=img_content, 
                                                    security_counter=sc,img_flags=0)
            img_hdr_list.append(img_hdr)
            ota_global_hdr = self.gen_ota_global_hdr(img_num=img_num, img_hdr_list=img_hdr_list, global_security_counter=0)
            offset = 0
            dst.seek(offset)
            dst.write(ota_global_hdr)

            offset = GLOBAL_HDR_LEN
            for img_hdr in img_hdr_list:
                dst.seek(offset)
                dst.write(img_hdr)
                offset += IMG_HDR_LEN

    def gen_ota_bin(self, ota_aes_en, security_counter):
        idx_list = self.get_pack_idx_list('ota.bin')
        if len(idx_list) == 0:
            logging.debug(f'Skip ota.bin gen')
            return

        if(self.is_overwrite()):
            self.gen_ota_bin_for_overwrite(security_counter)
        elif(self.is_xip()):
            self.gen_ota_bin_for_xip(ota_aes_en, security_counter)
        else:
            return

    def gen_ota_bin_for_test(self, sc):
        ota_sign_bin = 'ota_vmin_signed.bin'
        ota_bin = "ota_vmin.bin"
        self.add_ota_hdr("ota", ota_sign_bin, ota_bin, sc)

        ota_new_bin = "ota_new.bin"
        ota_error_bin = "ota_error.bin"
        shutil.copyfile(ota_sign_bin, ota_new_bin)
        with open(ota_new_bin, 'r+b') as file:
            file.seek(8)
            ih_hdr_size = struct.unpack('<H', file.read(2))[0]
            ih_protect_size = struct.unpack('<H', file.read(2))[0]
            ih_image_size = struct.unpack('<I', file.read(4))[0]
            signature_off = ih_hdr_size + ih_protect_size + ih_image_size + 0x44
            file.seek(signature_off)
            error = bytes([0xAA]*8)
            file.write(error)
        self.add_ota_hdr("ota", ota_new_bin, ota_error_bin, sc)

    def gen_ota_bin_for_overwrite(self, sc):
        ota_sign_bin = 'ota_signed.bin'
        ota_bin = 'ota.bin'

        if os.path.exists(ota_sign_bin) == False:
            logging.error(f'{ota_sign_bin} not exists, abort')
            exit(1)

        # Add OTA Hdr
        self.add_ota_hdr("ota", ota_sign_bin, ota_bin, sc)

    def gen_ota_bin_for_xip(self, ota_aes_en, sc):
        ota_sign_bin = 'ota_signed.bin'
        ota_bin = 'ota.bin'
        ota_partition = self.find_partition_by_name("primary_all")

        if ota_aes_en:
            aes_bin_name = "ota_aes.bin"

            aes_tool = get_flash_aes_tool()
            start_address = hex(phy2virtual(ota_partition.phy_partition_offset))
            cmd = f'{aes_tool} encrypt -infile {ota_sign_bin} -keywords {self.aes_key} -outfile {aes_bin_name} -startaddress {start_address}'
            run_cmd_not_check_ret(cmd)
            crc_bin_name = f'ota_aes_crc.bin'
            calc_crc16(aes_bin_name, crc_bin_name)

            ota_sign_bin = crc_bin_name

        size = os.path.getsize(ota_sign_bin)

        # Add OTA Hdr
        self.add_ota_hdr("primary_all", ota_sign_bin, ota_bin, sc)

    def parse_and_validate_pack_json(self, pack_json):
        if pack_json == None:
            logging.error('Invalid pack json')
            exit(1)

        self.pack_data = None
        with open(pack_json, 'r') as f:
            self.pack_json = json.load(f)

        self.all_pack_partitions = ['bl2', 'partition', 'primary_all']
        for k in self.pack_json:
            for v in self.pack_json[k]:
                p = self.find_partition_by_name(v)
                if p == None:
                    logging.error(f'{pack_json} has nonexist partition {v}')
                    exit(1)
                self.all_pack_partitions.append(p.partition_name)

    def is_partition_need_pack(self, p):
        if p.partition_name in self.all_pack_partitions:
            return True
        return False

    def get_pack_idx_list(self, pack_name):
        idx_list = []
        if pack_name not in self.pack_json:
            logging.debug(f'Pack bin {pack_name} not in pack.json, skip it')
            return idx_list

        for partition_name in self.pack_json[pack_name]:
            idx_list.append(self.partition_name_to_idx(partition_name))
        logging.debug(f'Partition id list of {pack_name}:{idx_list}')
        return idx_list

    def pack_bin(self, pack_json, aes_type, sigle_bin, aes_key, security_counter, ota_aes_en, boot_ota, pk_hash=True):
        self.aes_type = aes_type
        self.aes_key = aes_key
        self.sigle_bin = sigle_bin
        self.pk_hash = pk_hash
        self.parse_and_validate_partitions_after_build()
        self.parse_and_validate_pack_json(pack_json)
        self.process_bl1_control(boot_ota) #bl1_control depends on app (bl2.bin)
        self.process_manifest()
        self.process_partition_partition()
        self.process_boot_flag()
        self.process_nvs()
        self.process_encrypted()
        self.process_app_aes_crc()
        self.gen_ota_bin(ota_aes_en, security_counter)
        self.gen_bootloader_ota_bin()
        if (self.bl1_secureboot_en == True):
            self.gen_provisioning_bin()
        self.gen_all_apps_bin() #all_apps depends on nvs/encrypted/app etc

    def copy_file(self, file_name, dst):
        if os.path.exists(file_name):
            shutil.copy(file_name, f'{dst}/{file_name}')

    def install_bin(self):
        install_dir = 'install'
        os.makedirs(install_dir, exist_ok=True)
        self.copy_file('all-app.bin', install_dir)
        self.copy_file('ota.bin', install_dir)
        self.copy_file('bootloader.bin', install_dir)
        self.copy_file('bootloader_B.bin', install_dir)
        self.copy_file('bootloader_ota.bin', install_dir)
        self.copy_file('provision_pack.bin', install_dir)
        self.copy_file('otp_efuse_config.json', install_dir)
        self.copy_file('app.bin', install_dir)
        self.copy_file('pack_cmd_list.txt', install_dir)
