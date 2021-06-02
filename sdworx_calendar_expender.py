#!/usr/bin/python3
#
# Author: Matthieu Baerts
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os
import re
import io
from collections import OrderedDict
import datetime

cal_in = sys.argv[1]
cal_tmp = cal_in + ".tmp"
cal_out = cal_in + ".expended.ics"

DATE_START = "DTSTART"
DATE_END = "DTEND"
DATE_FORMAT = "%Y%m%d"
DESC = "DESCRIPTION"
SUMMARY = "SUMMARY"
EXTRA = "__EXTRA__"
END = "END"
MONDAY = 0
FRIDAY = 4

def print_line(line):
	print(line, file=fp_out, end="\n")

def beautify(value):
	title = value.title()
	title = re.sub(r'^Am ', "AM ", title)
	title = re.sub(r'^Pm ', "PM ", title)
	return title

def str_to_date(value):
	return datetime.datetime.strptime(value, DATE_FORMAT)

def date_to_str(date):
	return date.strftime(DATE_FORMAT)

# we need to cover the case: date is the last day of the month
def date_next_day_str(value):
	return date_to_str(str_to_date(value) + datetime.timedelta(days=1))

def get_weekday(value):
	return str_to_date(value).weekday()

def is_start_week(value):
	weekday = get_weekday(value)
	return weekday == MONDAY or weekday > FRIDAY

def is_end_week(value):
	return get_weekday(value) >= FRIDAY

def print_dict(event):
	if EXTRA in event:
		event[DESC] += ": " + str(event[EXTRA])
		event.pop(EXTRA)

	# always add an end date, needed for some calendars
	if not DATE_END in event:
		event[DATE_END] = event[DATE_START]
		# END:VEVENT needs to be at the end
		event.move_to_end(END)

	for key, value in event.items():
		if key == DESC or key == SUMMARY:
			value = beautify(value)
		# it seems we need to give date end +1
		if key == DATE_END:
			value = date_next_day_str(value)
		print_line(key + ":" + value)

	if key != END:
		print("Error: END is not at the end", event)

def get_date_str(event):
	return event[DATE_START]

def get_date_date(event):
	return str_to_date(get_date_str(event))

def get_date(event):
	return int(get_date_str(event))

def get_last_date_str(event):
	if DATE_END in event:
		return event[DATE_END]
	return get_date_str(event)

def get_last_date(event):
	return int(get_last_date_str(event))

def is_same_date(prev_event, new_event):
	return get_last_date_str(prev_event) == get_date_str(new_event)

def get_diff_date(prev_value, new_value):
	return (str_to_date(new_value) - str_to_date(prev_value)).days

def is_less_a_week(prev_value, new_value):
	return get_diff_date(prev_value, new_value) < 7

def is_next_date(prev_event, new_event):
	prev_date = get_last_date_str(prev_event)
	new_date = get_date_str(new_event)
	if date_next_day_str(prev_date) == new_date:
		return True
	if is_less_a_week(prev_date, new_date) and \
	   is_end_week(prev_date) and is_start_week(new_date):
		return True
	return False

def get_time(event):
	times = re.findall(r'\(([0-9]+)h\)', event[DESC])
	if times:
		return max(1, int(times[0]))

	days = re.findall(r'\(([0-9]+)d\)', event[DESC])
	if days:
		return int(days[0]) * 8

	# sometimes, there is no time: full/half day
	if re.search(r'^[AP]M ', event[SUMMARY]):
		return 4
	return 8

def is_full_day(event):
	return get_time(event) >= 7

def add_extra(event, desc, extra, nb):
	if not EXTRA in event:
		event[EXTRA] = []
	event[EXTRA].append(desc + ": " + extra + " [" + nb + "]")
	# END:VEVENT needs to be at the end
	event.move_to_end(END)

def replaced_time_str(prev_event, new_event):
	new_time = get_time(new_event)
	hours = get_time(prev_event) + new_time
	prev_event[SUMMARY] = re.sub(r'\([0-9]+h\)', '(' + str(hours) + 'h)', prev_event[SUMMARY])
	return new_time

def replace_day_str(prev_event, new_event):
	delta = get_date_date(new_event) - get_date_date(prev_event)
	days = delta.days + 1
	days_str = ' (' + str(days) + 'd)'
	search_dh = r' \([0-9]+[hd]\)'
	if re.search(search_dh, prev_event[SUMMARY]):
		prev_event[SUMMARY] = re.sub(search_dh, days_str, prev_event[SUMMARY])
	else:
		prev_event[SUMMARY] += days_str
	return get_date_str(new_event)

def add_time(prev_event, new_event):
	hours = replaced_time_str(prev_event, new_event)
	add_extra(prev_event, "add time", new_event[DESC], str(hours) + "h")

def merge_event(prev_event, new_event):
	prev_event[DATE_END] = get_date_str(new_event)
	date = replace_day_str(prev_event, new_event)
	add_extra(prev_event, "add date", new_event[DESC], date)

def get_desc(event):
	# without the time
	return re.sub(r' \([0-9]+h\)', '', event[DESC])

def is_same_desc(prev_event, new_event):
	return get_desc(prev_event) == get_desc(new_event)

def create_event(prev_event, new_event):
	if (prev_event):
		print_dict(prev_event)
	return new_event.copy()

def get_owner(value):
	# grep SUMMARY Calendar.ics | cut -d: -f2 | sed -e "s/ (.\+)//g" -e "s/^[PA]M //g" | sort -u
	# remove info in () and AM/PM
	value = re.sub(r' \(.+\)', '', value)
	value = re.sub(r'^[AP]M ', '', value)
	return value.lower()

def get_category(value):
	cat = "off"
	cats = re.findall(r'\(([a-z ]+)\)', value.lower())
	if cats:
		cat = cats[0]
		if len(cats) > 1:
			print("ERROR: found more than one cat: ", cats)
	return re.sub(r'\s+', '', cat.title())

def print_all(owners):
	for owner, types in sorted(owners.items()):
		totals = {}
		for cat, dates in sorted(types.items()):
			totals[cat] = 0
			for date, events in sorted(dates.items()):
				for event in events:
					totals[cat] += 1
					for key, value in event.items():
						print_line(key + ":" + value)
		print(owner, ": total:", sum(totals.values()), ", events: ", totals)

owners = {}
event = None
fp_out = io.open(cal_tmp, 'w')

with io.open(cal_in, 'r') as fp_in:
	for line in fp_in:
		line = line.rstrip()
		key, value = line.split(":", 1)
		
		# find the first event
		if not event:
			if line == "BEGIN:VEVENT":
				event = OrderedDict()
			else:
				# need to be the last line
				if line == "END:VCALENDAR":
					print_all(owners)
				print_line(line)
				continue

		event[key] = value

		if key == END:
			if value == "VEVENT":
				owner = get_owner(event[SUMMARY])
				date = get_date(event)
				cat = get_category(event[SUMMARY])
				if not owner in owners:
					owners[owner] = {}
				# filter per category to support mix of events
				if not cat in owners[owner]:
					owners[owner][cat] = {}
				# we can have multiple events for the same owner the same day
				if not date in owners[owner][cat]:
					owners[owner][cat][date] = []
				owners[owner][cat][date].append(event)
				event = None
			else:
				print("Error: " + line)

fp_out.close()

in_event = False
new_event = None
prev_event = None
fp_out = io.open(cal_out, 'w', encoding='utf-8')

with io.open(cal_tmp, 'r') as fp_in:
	for line in fp_in:
		line = line.rstrip()
		key, value = line.split(":", 1)

		# find the first event
		if not in_event:
			if line == "BEGIN:VEVENT":
				in_event = True
				new_event = OrderedDict()
			else:
				# need to be the last line
				if line == "END:VCALENDAR":
					print_dict(prev_event)
				print_line(line)
				continue

		new_event[key] = value

		if key == END:
			if value == "VEVENT":
				in_event = False
				if not prev_event:
					prev_event = create_event(prev_event, new_event)
				elif is_same_desc(prev_event, new_event):
					if is_same_date(prev_event, new_event):
						add_time(prev_event, new_event)
					elif is_full_day(prev_event) and \
					     is_next_date(prev_event, new_event):
						merge_event(prev_event, new_event)
					else:
						prev_event = create_event(prev_event, new_event)
				else:
					prev_event = create_event(prev_event, new_event)
				new_event = None
			else:
				print("Error: " + line)
				break

fp_out.close()
os.remove(cal_tmp)
