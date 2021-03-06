#   ____  _  __
#  / ___|| |/ /__ _ _ __ _ __ ___   __ _
#  \___ \| ' // _` | '__| '_ ` _ \ / _` |
#   ___) | . \ (_| | |  | | | | | | (_| |
#  |____/|_|\_\__,_|_|  |_| |_| |_|\__,_|
#
# Yet another carma bot for telegram
# Copyright (C) 2020 Nikita Serba. All rights reserved
# https://github.com/sandsbit/skarmabot
#
# SKarma is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# SKarma is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with SKarma. If not, see <https://www.gnu.org/licenses/>.

import datetime
import logging
import codecs
import operator

from math import inf
from configparser import ConfigParser, SectionProxy
from os import path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from deprecated import deprecated

from skarma.utils.singleton import SingletonMeta
from skarma.utils import algo


class ConfigParseError(Exception):
    pass


@dataclass
class KarmaRange:
    """Karma range structure"""

    name: str

    min_range: float
    max_range: float

    enable_plus: bool
    enable_minus: bool

    plus_value: int
    minus_value: int

    day_max: float
    timeout: datetime.timedelta

    @deprecated('Use binary search on sorted array instead')
    def karma_in_range(self, karma: float) -> bool:
        """Check if user with given karma fits that karma range"""

        return (karma >= self.min_range) and (karma <= self.max_range)

    @staticmethod
    def _read_int_or_inf(from_: str) -> float:
        if from_ == 'oo' or from_ == '+oo':
            return inf
        elif from_ == '-oo':
            return -inf
        else:
            return int(from_)

    @classmethod
    def range_from_parsed_config(cls, parsed: SectionProxy):
        """Create KarmaRange from parsed section"""
        blog = logging.getLogger('botlog')
        blog.info(f'Parsing section {parsed.name}')

        timeout_v = int(parsed['timeout'][:-1])
        timeout_s = parsed['timeout'][-1]

        if timeout_s == 's':
            timeout = datetime.timedelta(seconds=timeout_v)
        elif timeout_s == 'm':
            timeout = datetime.timedelta(minutes=timeout_v)
        elif timeout_s == 'h':
            timeout = datetime.timedelta(hours=timeout_v)
        elif timeout_s == 'd':
            timeout = datetime.timedelta(days=timeout_v)
        elif timeout_s == 'w':
            timeout = datetime.timedelta(weeks=timeout_v)
        else:
            raise ConfigParseError('Invalid timeout symbol: ' + timeout_s)

        try:
            obj = cls(
                name=parsed['name'],
                min_range=cls._read_int_or_inf(parsed['range_min']),
                max_range=cls._read_int_or_inf(parsed['range_max']),
                enable_plus=parsed.getboolean('enable_plus'),
                enable_minus=parsed.getboolean('enable_minus'),
                plus_value=parsed.getint('plus_value'),
                minus_value=parsed.getint('minus_value'),
                day_max=cls._read_int_or_inf(parsed['day_max']),
                timeout=timeout
            )
        except KeyError as e:
            msg = f'Value of {str(e)} not found for section {parsed.name}'
            blog.fatal(msg)
            raise ConfigParseError(msg)
        return obj

    def __lt__(self, other: int) -> bool:
        """Check that int is less than karma range min"""
        return other < self.min_range

    def __eq__(self, other: int) -> bool:
        """Check that int is in that karma range"""
        return self.min_range <= other <= self.max_range


class KarmaRangesManager(metaclass=SingletonMeta):
    """Checks user's karma range. Karma ranges are loaded from karma.conf"""

    blog = logging.getLogger('botlog')

    KARMA_CONFIG_FILE = path.join(path.dirname(path.abspath(__file__)), '../config/karma.conf')

    default_range: KarmaRange
    ranges: List[KarmaRange] = []

    def __init__(self) -> None:
        """
        Parse all sections of karma.conf

        If any karma ranges overlap, ConfigParseError will be raised.
        """

        self.blog.info('Starting parsing karma.conf, that is located in ' + self.KARMA_CONFIG_FILE)

        if not path.isfile(self.KARMA_CONFIG_FILE):
            msg = "Couldn't find karma config file path: " + self.KARMA_CONFIG_FILE
            self.blog.fatal(msg)
            raise FileNotFoundError(msg)

        app_config = ConfigParser()
        app_config.read_file(codecs.open(self.KARMA_CONFIG_FILE, 'r', 'utf8'))

        self.blog.debug('Successfully read karma config file')

        for section in app_config.sections():
            self.ranges.append(KarmaRange.range_from_parsed_config(app_config[section]))

        self.ranges.sort(key=operator.attrgetter('min_range'))

        res = self._static_ranges_check()
        if res is not None:
            msg = f'Ranges "{res[0]}" and "{res[1]}" overlap'
            self.blog.fatal(msg)
            raise ConfigParseError(msg)

        self.default_range = KarmaRange.range_from_parsed_config(app_config['DEFAULT'])

    def get_range_by_karma(self, karma: int) -> KarmaRange:
        """
        Return KarmaRange object with parsed karma range for given karma.
        If no ranges contain given karma level, ConfigParseError will be raised.
        """

        self.blog.debug(f'Parsing range for karma: {karma}')

        try:
            return self.ranges[algo.binary_search(karma, self.ranges)]
        except algo.NotFound:
            msg = f'No ranges contain karma: {karma}'
            self.blog.fatal(msg)
            raise ConfigParseError(msg)

    def _static_ranges_check(self) -> Optional[Tuple[str, str]]:
        """
        Check that ranges does not overlap.

        returns None, if ranges does not overlap.
        if ranges overlap, returns Tuple which contains names of ranges, that overlap.
        """

        for i in range(1, len(self.ranges)):
            if self.ranges[i].min_range <= self.ranges[i-1].max_range:
                return self.ranges[i].name, self.ranges[i - 1].name

        return None
