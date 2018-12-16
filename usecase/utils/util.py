import datetime
import logging
import os
import os.path
import re
import simplejson as json
import sys

from oslo_config import cfg

from usecase.utils import settings


CONF = cfg.ConfigOpts()
logger = logging.getLogger(__name__)


def init(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    CONF(
        argv,
        'usecase',
        default_config_dirs=[settings.CONFIG_DIR]
    )


def load_config(filename):
    abs_path = os.path.join(settings.CONFIG_DIR, filename)
    with open(abs_path) as config_file:
        content = config_file.read()
        return json.loads(content)
    return None


def parse_datetime(date_time, exception_class=Exception):
    try:
        return datetime.datetime.strptime(
            date_time, '%Y-%m-%d %H:%M:%S'
        )
    except Exception as error:
        logging.exception(error)
        raise exception_class(
            'date time %s format is invalid' % date_time
        )


def parse_datetime_range(date_time_range, exception_class=Exception):
    try:
        start, end = date_time_range.split(',')
    except Exception as error:
        logging.exception(error)
        raise exception_class(
            'there is no `,` in date time range %s' % date_time_range
        )
    if start:
        start_datetime = parse_datetime(start, exception_class)
    else:
        start_datetime = None
    if end:
        end_datetime = parse_datetime(end, exception_class)
    else:
        end_datetime = None
    return start_datetime, end_datetime


def parse_time_interval(time_interval_str):
    if not time_interval_str:
        return 0

    time_interval_tuple = [
        time_interval_element
        for time_interval_element in time_interval_str.split(' ')
        if time_interval_element
    ]
    time_interval_dict = {}
    time_interval_unit_mapping = {
        'd': 'days',
        'w': 'weeks',
        'h': 'hours',
        'm': 'minutes',
        's': 'seconds'
    }
    for time_interval_element in time_interval_tuple:
        mat = re.match(r'^([+-]?\d+)(w|d|h|m|s).*', time_interval_element)
        if not mat:
            continue

        time_interval_value = int(mat.group(1))
        time_interval_unit = time_interval_unit_mapping[mat.group(2)]
        time_interval_dict[time_interval_unit] = (
            time_interval_dict.get(time_interval_unit, 0) + time_interval_value
        )

    time_interval = datetime.timedelta(**time_interval_dict)
    if sys.version_info[0:2] > (2, 6):
        return time_interval.total_seconds()
    else:
        return (
            time_interval.microseconds + (
                time_interval.seconds + time_interval.days * 24 * 3600
            ) * 1e6
        ) / 1e6
