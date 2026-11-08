// SPDX-License-Identifier: GPL-2.0
/*
 * Touch input boost for the Galaxy M30s (Exynos 9611, kernel 4.14).
 * The Samsung booster lives in One UI userspace and is gone on a GSI, so do it here:
 * on touch activity raise the minimum frequency of both CPU clusters (PM QoS) for a short time.
 * Tunables: /sys/module/input_boost_m30s/parameters/{enabled,duration_ms,little_khz,big_khz}
 */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/init.h>
#include <linux/input.h>
#include <linux/slab.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/mutex.h>
#include <linux/pm_qos.h>

static bool enabled = true;
static uint duration_ms = 150;
static uint little_khz = 1352000;	/* cluster 0, cpus 0-3 (A53); the request is rounded up to a real OPP */
static uint big_khz = 1456000;		/* cluster 1, cpus 4-7 (A73) */
module_param(enabled, bool, 0644);
module_param(duration_ms, uint, 0644);
module_param(little_khz, uint, 0644);
module_param(big_khz, uint, 0644);

static struct pm_qos_request little_req, big_req;
static struct work_struct on_work;
static struct delayed_work off_work;
static DEFINE_MUTEX(lock);
static bool active;
static unsigned long last_kick;

static void ib_on(struct work_struct *w)
{
	mutex_lock(&lock);
	if (!active) {
		pm_qos_update_request(&little_req, little_khz);
		pm_qos_update_request(&big_req, big_khz);
		active = true;
	}
	mod_delayed_work(system_highpri_wq, &off_work, msecs_to_jiffies(duration_ms));
	mutex_unlock(&lock);
}

static void ib_off(struct work_struct *w)
{
	mutex_lock(&lock);
	pm_qos_update_request(&little_req, PM_QOS_DEFAULT_VALUE);
	pm_qos_update_request(&big_req, PM_QOS_DEFAULT_VALUE);
	active = false;
	mutex_unlock(&lock);
}

static void ib_event(struct input_handle *handle, unsigned int type, unsigned int code, int value)
{
	if (!enabled || type != EV_ABS)
		return;
	/* touch down (new tracking id) or finger movement; at most one kick per 20 ms */
	if (code != ABS_MT_TRACKING_ID && code != ABS_MT_POSITION_X && code != ABS_MT_POSITION_Y)
		return;
	if (time_before(jiffies, last_kick + msecs_to_jiffies(20)))
		return;
	last_kick = jiffies;
	queue_work(system_highpri_wq, &on_work);
}

static int ib_connect(struct input_handler *handler, struct input_dev *dev, const struct input_device_id *id)
{
	struct input_handle *handle;
	int ret;

	handle = kzalloc(sizeof(*handle), GFP_KERNEL);
	if (!handle)
		return -ENOMEM;
	handle->dev = dev;
	handle->handler = handler;
	handle->name = "input_boost_m30s";
	ret = input_register_handle(handle);
	if (ret)
		goto err_free;
	ret = input_open_device(handle);
	if (ret)
		goto err_unreg;
	return 0;
err_unreg:
	input_unregister_handle(handle);
err_free:
	kfree(handle);
	return ret;
}

static void ib_disconnect(struct input_handle *handle)
{
	input_close_device(handle);
	input_unregister_handle(handle);
	kfree(handle);
}

static const struct input_device_id ib_ids[] = {
	{	/* multitouch screens */
		.flags = INPUT_DEVICE_ID_MATCH_EVBIT | INPUT_DEVICE_ID_MATCH_ABSBIT,
		.evbit = { BIT_MASK(EV_ABS) },
		.absbit = { [BIT_WORD(ABS_MT_POSITION_X)] = BIT_MASK(ABS_MT_POSITION_X) | BIT_MASK(ABS_MT_POSITION_Y) },
	},
	{ },
};

static struct input_handler ib_handler = {
	.event = ib_event,
	.connect = ib_connect,
	.disconnect = ib_disconnect,
	.name = "input_boost_m30s",
	.id_table = ib_ids,
};

static int __init ib_init(void)
{
	INIT_WORK(&on_work, ib_on);
	INIT_DELAYED_WORK(&off_work, ib_off);
	pm_qos_add_request(&little_req, PM_QOS_CLUSTER0_FREQ_MIN, PM_QOS_DEFAULT_VALUE);
	pm_qos_add_request(&big_req, PM_QOS_CLUSTER1_FREQ_MIN, PM_QOS_DEFAULT_VALUE);
	return input_register_handler(&ib_handler);
}
late_initcall(ib_init);
