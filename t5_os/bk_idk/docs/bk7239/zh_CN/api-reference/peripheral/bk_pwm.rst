PWM
================

:link_to_translation:`en:[English]`

PWM API Status
------------------

+----------------------------------------------+---------+------------+
| API                                          | BK7239  | BK7239_cp1 |
+==============================================+=========+============+
| :cpp:func:`bk_pwm_driver_init`               | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_driver_deinit`             | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_init`                      | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_deinit`                    | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_set_duty_period`           | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_start`                     | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_stop`                      | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_set_init_signal_low`       | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_set_init_signal_high`      | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_register_isr`              | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_enable_interrupt`          | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_disable_interrupt`         | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_group_init`                | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_group_deinit`              | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_group_start`               | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_group_stop`                | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_capture_init`              | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_capture_deinit`            | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_capture_start`             | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_capture_stop`              | Y       | Y          |
+----------------------------------------------+---------+------------+
| :cpp:func:`bk_pwm_capture_get_value`         | Y       | Y          |
+----------------------------------------------+---------+------------+


PWM Channel Number
------------------------

+----------------+---------+------------+
| Capability     | BK7239  | BK7239_cp1 |
+================+=========+============+
| Channel Number | 6       | 6          |
+----------------+---------+------------+

PWM Group Support
-------------------------

+----------------+---------+------------+
| Capability     | BK7239  | BK7239_cp1 |
+================+=========+============+
| Software Group | Y       | Y          |
+----------------+---------+------------+
| Hardware Group | Y       | Y          |
+----------------+---------+------------+


PWM Duty Support
-------------------------

+-------------------+---------+------------+
| Capability        | BK7239  | BK7239_cp1 |
+===================+=========+============+
| period_cycle      | Y       | Y          |
+-------------------+---------+------------+
| duty_cycle        | Y       | Y          |
+-------------------+---------+------------+
| duty2_cycle       | Y       | Y          |
+-------------------+---------+------------+
| duty3_cycle       | Y       | Y          |
+-------------------+---------+------------+

For unsupported duty fileds, we should set them to 0.

PWM Capture Edge Support Status
--------------------------------

+-------------------+---------+------------+
| Capability        | BK7239  | BK7239_cp1 |
+===================+=========+============+
| PWM_CAPTURE_POS   | Y       | Y          |
+-------------------+---------+------------+
| PWM_CAPTURE_NEG   | Y       | Y          |
+-------------------+---------+------------+
| PWM_CAPTURE_EDGE  | Y       | Y          |
+-------------------+---------+------------+

PWM Channel and GPIO Map
---------------------------------

+-------------------+---------+------------+
| Channel Number    | BK7239  | BK7239_cp1 |
+===================+=========+============+
| 0                 | 6       | 6          |
+-------------------+---------+------------+
| 1                 | 7       | 7          |
+-------------------+---------+------------+
| 2                 | 8       | 8          |
+-------------------+---------+------------+
| 3                 | 9       | 9          |
+-------------------+---------+------------+
| 4                 | 24      | 24         |
+-------------------+---------+------------+
| 5                 | 25      | 25         |
+-------------------+---------+------------+
| 6                 | 32      | 32         |
+-------------------+---------+------------+
| 7                 | 33      | 33         |
+-------------------+---------+------------+
| 8                 | 34      | 34         |
+-------------------+---------+------------+
| 9                 | 35      | 35         |
+-------------------+---------+------------+
| 10                | 36      | 36         |
+-------------------+---------+------------+
| 11                | 37      | 37         |
+-------------------+---------+------------+

If the channel has more than one GPIO to map, the channel init API will choose the smallest GPIO port as the default
value. We can call bk_pwm_set_gpio() to change it after the init API is called.

PWM API Reference
---------------------

.. include:: ../../_build/inc/pwm.inc

PWM API Typedefs
---------------------
.. include:: ../../_build/inc/pwm_types.inc
.. include:: ../../_build/inc/hal_pwm_types.inc


