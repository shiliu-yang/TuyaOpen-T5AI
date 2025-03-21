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

#include <os/os.h>
#include <stdio.h>
#include <os/mem.h>
#include <components/log.h>

#include <driver/psram.h>
#include "frame_buffer.h"

#include "media_evt.h"
#include "storage_act.h"

#define TAG "storage_major"

#define LOGI(...) BK_LOGW(TAG, ##__VA_ARGS__)
#define LOGW(...) BK_LOGW(TAG, ##__VA_ARGS__)
#define LOGE(...) BK_LOGE(TAG, ##__VA_ARGS__)
#define LOGD(...) BK_LOGD(TAG, ##__VA_ARGS__)

static beken_queue_t storage_major_task_queue = NULL;
static beken_thread_t storage_major_task_thread = NULL;
static beken_semaphore_t storage_major_sem = NULL;
static storage_info_t storage_major_info;

static bk_err_t storage_major_task_send_msg(uint8_t msg_type, uint32_t data)
{
	bk_err_t ret;
	storages_task_msg_t msg;

	if (storage_major_task_queue)
	{
		msg.type = msg_type;
		msg.data = data;

		ret = rtos_push_to_queue(&storage_major_task_queue, &msg, BEKEN_NO_WAIT);
		if (BK_OK != ret)
		{
			LOGE("storage_major_task_queue failed\r\n");
			return kOverrunErr;
		}

		return ret;
	}
	return kNoResourcesErr;
}

static void storage_frame_major_notify_app(uint32_t param)
{
	frame_buffer_t *frame = NULL;

	storage_major_info.capture_state = STORAGE_STATE_ENABLED;

	frame = frame_buffer_fb_read(MODULE_CAPTURE);

	if (frame == NULL)
	{
		LOGE("read frame NULL\n");
		return;
	}

	msg_send_req_to_media_major_mailbox_sync(EVENT_VID_CAPTURE_NOTIFY, APP_MODULE, (uint32_t)frame, NULL);

	frame_buffer_fb_free(frame, MODULE_CAPTURE);

	msg_send_rsp_to_media_major_mailbox((media_mailbox_msg_t *)param, BK_OK, APP_MODULE);

	storage_major_info.capture_state = STORAGE_STATE_DISABLED;
}

static void storage_video_major_notify_app(uint32_t param)
{
	frame_buffer_t *frame = NULL;

	msg_send_rsp_to_media_major_mailbox((media_mailbox_msg_t *)param, BK_OK, APP_MODULE);

	storage_major_info.capture_state = STORAGE_STATE_ENABLED;

	while (storage_major_info.capture_state == STORAGE_STATE_ENABLED)
	{
		frame = frame_buffer_fb_read(MODULE_CAPTURE);

		if (frame == NULL)
		{
			LOGE("read frame NULL\n");
			continue;
		}

		msg_send_req_to_media_major_mailbox_sync(EVENT_VID_SAVE_ALL_NOTIFY, APP_MODULE, (uint32_t)frame, NULL);

		frame_buffer_fb_free(frame, MODULE_CAPTURE);
	};

	if (storage_major_sem)
	{
		rtos_set_semaphore(&storage_major_sem);
	}
}

static void storage_video_major_notify_app_stop(uint32_t param)
{
	if (rtos_get_semaphore(&storage_major_sem, BEKEN_WAIT_FOREVER))
	{
		LOGE("%s wait semaphore failed\n", __func__);
	}

	msg_send_rsp_to_media_major_mailbox((media_mailbox_msg_t *)param, BK_OK, APP_MODULE);
}

static void storage_major_deinit(uint32_t param)
{

	if (storage_major_sem)
	{
		rtos_deinit_semaphore(&storage_major_sem);
		storage_major_sem = NULL;
	}

	storage_major_info.state = STORAGE_STATE_DISABLED;
	storage_major_info.capture_state = STORAGE_STATE_DISABLED;

	msg_send_rsp_to_media_major_mailbox((media_mailbox_msg_t *)param, BK_OK, APP_MODULE);
}

static void storage_major_task_entry(beken_thread_arg_t data)
{
	bk_err_t ret = BK_OK;

	storages_task_msg_t msg;

	while (1)
	{
		ret = rtos_pop_from_queue(&storage_major_task_queue, &msg, BEKEN_WAIT_FOREVER);

		if (ret == BK_OK)
		{
			switch (msg.type)
			{
				case STORAGE_TASK_CAPTURE:
					storage_frame_major_notify_app(msg.data);
					break;

				case STORAGE_TASK_SAVE:
					storage_video_major_notify_app(msg.data);
					break;

				case STORAGE_TASK_SAVE_STOP:
					storage_video_major_notify_app_stop(msg.data);
					break;

				case STORAGE_TASK_EXIT:
					storage_major_deinit(msg.data);
					goto exit;

				default:
					break;
			}
		}
	}

exit:

	LOGI("storage_major_task exit success!\r\n");

	rtos_deinit_queue(&storage_major_task_queue);
	storage_major_task_queue = NULL;

	storage_major_task_thread = NULL;
	rtos_delete_thread(NULL);
}

static bk_err_t storage_major_task_init(uint32_t param)
{
	int ret = BK_OK;

	if (storage_major_sem == NULL)
	{
		ret = rtos_init_semaphore_ex(&storage_major_sem, 1, 0);

		if (ret != BK_OK)
		{
			LOGE("%s, init semaphore failed\r\n", __func__);
			storage_major_sem = NULL;
			goto error;
		}
	}


	if ((!storage_major_task_queue) && (!storage_major_task_thread))
	{
		ret = rtos_init_queue(&storage_major_task_queue,
								"storage_major_task_queue",
								sizeof(storages_task_msg_t),
								10);

		if (BK_OK != ret)
		{
			LOGE("%s storage_major_task_queue init failed\n", __func__);
			goto error;
		}

		storage_major_info.param = param;

		if (param == FB_INDEX_JPEG)
			frame_buffer_fb_register(MODULE_CAPTURE, FB_INDEX_JPEG);
		else
			frame_buffer_fb_register(MODULE_CAPTURE, FB_INDEX_H264);

		ret = rtos_create_thread(&storage_major_task_thread,
		                         BEKEN_DEFAULT_WORKER_PRIORITY,
		                         "storage_major_task_thread",
		                         (beken_thread_function_t)storage_major_task_entry,
		                         1024,
		                         NULL);

		if (BK_OK != ret)
		{
			LOGE("%s storage_major_task_thread init failed\n", __func__);
			ret = BK_ERR_NO_MEM;
			goto error;
		}
	}

	return ret;

error:

	frame_buffer_fb_deregister(MODULE_CAPTURE, storage_major_info.param);

	if (storage_major_sem)
	{
		rtos_deinit_semaphore(&storage_major_sem);
		storage_major_sem = NULL;
	}

	if (storage_major_task_queue)
	{
		rtos_deinit_queue(&storage_major_task_queue);
		storage_major_task_queue = NULL;
	}

	if (storage_major_task_thread)
	{
		storage_major_task_thread = NULL;
		rtos_delete_thread(NULL);
	}

	return ret;
}

static bk_err_t storage_major_task_open_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	if (get_storage_state() == STORAGE_STATE_ENABLED)
	{
		LOGI("%s already open\r\n", __func__);
		goto end;
	}
	else
	{
		storage_init();

		ret = storage_major_task_init(msg->param);

		if (ret != BK_OK)
		{
			storage_major_info.state = STORAGE_STATE_DISABLED;
		}
		else
		{
			storage_major_info.state = STORAGE_STATE_ENABLED;
		}
	}

end:

	msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);

	LOGI("%s complete\n", __func__);

	return ret;
}

static bk_err_t storage_major_task_close_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	if (get_storage_state() == STORAGE_STATE_DISABLED)
	{
		LOGI("%s already close\r\n", __func__);
		msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
	}
	else
	{
		storage_major_info.capture_state = STORAGE_STATE_DISABLED;

		frame_buffer_fb_deregister(MODULE_CAPTURE, storage_major_info.param);

		storage_major_task_send_msg(STORAGE_TASK_EXIT, (uint32_t)msg);
	}

	return ret;
}

static bk_err_t storage_major_capture_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	if (storage_major_info.state != STORAGE_STATE_ENABLED)
	{
			LOGE("%s storage major task not open\r\n", __func__);
			ret = kGeneralErr;
			msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
			return ret;
	}

	if (storage_major_info.capture_state == STORAGE_STATE_ENABLED)
	{
		LOGE("%s capture busy\r\n", __func__);
		msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
	}
	else
	{
		ret = storage_major_task_send_msg(STORAGE_TASK_CAPTURE, (uint32_t)msg);
	}

	return ret;
}

static bk_err_t storage_major_video_save_start_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	if (storage_major_info.state != STORAGE_STATE_ENABLED)
	{
			LOGE("%s storage major task not open\r\n", __func__);
			ret = kGeneralErr;
			msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
			return ret;
	}

	if (storage_major_info.capture_state == STORAGE_STATE_ENABLED)
	{
		LOGE("%s save video busy\r\n", __func__);
		msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
	}
	else
	{
		storage_major_info.capture_state = STORAGE_STATE_ENABLED;
		ret = storage_major_task_send_msg(STORAGE_TASK_SAVE, (uint32_t)msg);
	}

	return ret;
}

static bk_err_t storage_major_video_save_stop_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	if (storage_major_info.capture_state == STORAGE_STATE_DISABLED)
	{
		LOGI("%s, alread stop save video\r\n", __func__);
		msg_send_rsp_to_media_major_mailbox(msg, ret, APP_MODULE);
	}
	else
	{
		storage_major_info.capture_state = STORAGE_STATE_DISABLED;

		storage_major_task_send_msg(STORAGE_TASK_SAVE_STOP, (uint32_t)msg);
	}

	return ret;
}

bk_err_t storage_major_event_handle(media_mailbox_msg_t *msg)
{
	int ret = BK_OK;

	switch (msg->event)
	{
		case EVENT_STORAGE_OPEN_IND:
			ret = storage_major_task_open_handle(msg);
			break;

		case EVENT_STORAGE_CLOSE_IND:
			ret = storage_major_task_close_handle(msg);
			break;

		case EVENT_STORAGE_CAPTURE_IND:
			ret = storage_major_capture_handle(msg);
			break;

		case EVENT_STORAGE_SAVE_START_IND:
			ret = storage_major_video_save_start_handle(msg);
			break;

		case EVENT_STORAGE_SAVE_STOP_IND:
			ret = storage_major_video_save_stop_handle(msg);
			break;

		default:
			break;
	}

	return ret;
}


media_storage_state_t get_storage_state(void)
{
	return storage_major_info.state;
}

void set_storage_state(media_storage_state_t state)
{
	storage_major_info.state = state;
}

void storage_init(void)
{
	os_memset(&storage_major_info, 0, sizeof(storage_info_t));

	storage_major_info.state = STORAGE_STATE_DISABLED;
	storage_major_info.capture_state = STORAGE_STATE_DISABLED;
}


