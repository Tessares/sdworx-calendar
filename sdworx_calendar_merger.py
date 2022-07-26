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
import pytz

cal_in = sys.argv[1]
cal_tmp = cal_in + ".tmp"
cal_out = cal_in + ".merged.ics"

DATE_START = "DTSTART"
DATE_END = "DTEND"
ORIG_DATE_START = "ORIG" + DATE_START
ORIG_DATE_END = "ORIG" + DATE_END
DATE_FORMAT = "%Y%m%d"
DATE_FORMAT_FULL = "%Y%m%dT%H%M%SZ" # 20210720T140000Z
DESC = "DESCRIPTION"
SUMMARY = "SUMMARY"
EXTRA = "__EXTRA__"
END = "END"
MONDAY = 0
FRIDAY = 4

BRUSSELS = pytz.timezone('Europe/Brussels')

def print_line(line):
	print(line, file=fp_out, end="\n")

def beautify(value):
	title = value.title()
	title = re.sub(r'^Am ', "AM ", title)
	title = re.sub(r'^Pm ', "PM ", title)
	return title

def str_to_date_full(value):
	date_parsed = datetime.datetime.strptime(value, DATE_FORMAT_FULL)
	date_utc = date_parsed.replace(tzinfo=datetime.timezone.utc)
	date_to_cet = date_utc.astimezone(BRUSSELS)
	return date_to_cet

def str_to_date(value):
	return datetime.datetime.strptime(value, DATE_FORMAT)

def date_to_str(date):
	return date.strftime(DATE_FORMAT)

# we need to cover the case: date is the last day of the month
def date_next_day_str(value):
	return date_to_str(str_to_date(value) + datetime.timedelta(days=1))

def date_prev_day_str(value):
	return date_to_str(str_to_date(value) - datetime.timedelta(days=1))

def get_weekday(value):
	return str_to_date(value).weekday()

def is_start_week(value):
	weekday = get_weekday(value)
	return weekday == MONDAY or weekday > FRIDAY

def is_end_week(value):
	return get_weekday(value) >= FRIDAY

def replaced_time_key(event, hours, key):
	event[key] = re.sub(r'\([0-9]+h\)', '(' + str(hours) + 'h)', event[key])

def replace_day_key(event, days, key):
	days_str = ' (' + str(days) + 'd)'
	search_dh = r' \([0-9]+[hd]\)'
	if re.search(search_dh, event[key]):
		event[key] = re.sub(search_dh, days_str, event[key])
	else:
		event[key] += days_str

def get_num_parenthesis(value, key):
	num = re.findall(r'\(([0-9]+)' + key + '\)', value)
	if num:
		return max(1, int(num[0])) # not to ignore < 1h events
	return 0

def get_hours(value):
	return get_num_parenthesis(value, 'h')

def get_days(value):
	return get_num_parenthesis(value, 'd')

def clean_event(event):
	# always add an end date, needed for us later (and for some calendars)
	if not DATE_END in event:
		# we cover a whole day, we need to give start date +1
		event[DATE_END] = date_next_day_str(event[DATE_START])
		# END:VEVENT needs to be at the end
		event.move_to_end(END)

	exact_start = None
	if ORIG_DATE_START in event:
		exact_start = str_to_date_full(event[ORIG_DATE_START])
		event.pop(ORIG_DATE_START)

	exact_end = None
	if ORIG_DATE_END in event:
		exact_end = str_to_date_full(event[ORIG_DATE_END])
		event.pop(ORIG_DATE_END)

	if exact_start and exact_end:
		delta = exact_end - exact_start
		days = delta.days
		# ideally round() but sdworx is doing int()
		hours = int(delta.seconds / 3600)

		# 7h or more == 1 day of work
		if hours >= 7:
			days += 1
			if hours > 9: # handle timezone difference: +1 hour
				print("WARNING: more than 9 hours", days, hours, exact_start, exact_end, event)
			else:
				hours = 0

		if days > 0:
			# there is a bug in the Calendar we get: hours is written in
			# the text but the event is taking more than a day
			if hours > 0:
				event[SUMMARY] += "?"
				event[DESC] += " hours: " + str(hours)
				print("WARNING: one day or more (" + str(days) + ") but for hourly event (" + str(hours) + ") " + str(exact_start) + " -> " + str(exact_end) + ": +1 day\n", event)
				days += 1

			replace_day_key(event, days, SUMMARY)
			replace_day_key(event, days, DESC)
		else:
			if hours <= 4:
				half = 'AM' if exact_start.hour < 12 else 'PM'
				event[SUMMARY] = half + ' ' + event[SUMMARY]

			replaced_time_key(event, hours, SUMMARY)
			replaced_time_key(event, hours, DESC)

	elif get_hours(event[SUMMARY]) >= 7:
		replace_day_key(event, 1, SUMMARY)

def print_key_val(key, val):
	print_line(key + ":" + val)

def print_dict(event):
	# merge extra
	if EXTRA in event:
		event[DESC] += ": " + str(event[EXTRA])
		event.pop(EXTRA)

	for key, value in event.items():
		if key == DESC or key == SUMMARY:
			value = beautify(value)

		print_key_val(key, value)

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
		# with whole day events, end date is "midnight the day after"
		return date_prev_day_str(event[DATE_END])

	print("ERROR: event has no end date", event)
	return get_date_str(event)

def get_last_date(event):
	return int(get_last_date_str(event))

def get_last_date_after_date(event):
	return str_to_date(date_next_day_str(get_last_date_str(event)))

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
	hours = get_hours(event[SUMMARY])
	if hours:
		return hours

	days = get_days(event[SUMMARY])
	if days:
		return days * 8

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
	replaced_time_key(prev_event, hours, SUMMARY)
	return new_time

def replace_day_str(prev_event, new_event):
	delta = get_last_date_after_date(new_event) - get_date_date(prev_event)
	replace_day_key(prev_event, delta.days, SUMMARY)
	return get_date_str(new_event)

def add_time(prev_event, new_event):
	hours = replaced_time_str(prev_event, new_event)
	add_extra(prev_event, "add time", new_event[DESC], str(hours) + "h")

def merge_event(prev_event, new_event):
	prev_event[DATE_END] = new_event[DATE_END]
	date = replace_day_str(prev_event, new_event)
	add_extra(prev_event, "add date", new_event[DESC], date)

def get_desc(event):
	# without the time and lower
	return re.sub(r' \([0-9]+[dh]\)', '', event[DESC]).lower()

def is_same_desc(prev_event, new_event):
	return get_desc(prev_event) == get_desc(new_event)

def create_event(prev_event, new_event):
	if (prev_event):
		print_dict(prev_event)
	return new_event.copy()

def get_owner(value):
	# grep SUMMARY Calendar.ics | cut -d: -f2 | sed -e "s/ (.\+)//g" -e "s/^[PA]M //g" | sort -u
	# remove info in () and AM/PM
	value = re.sub(r' \(.+\)\?*', '', value)
	value = re.sub(r'^[AP]M ', '', value)
	return value.lower()

def get_category(value):
	cat = "off"
	cats = re.findall(r'\(([a-z][^\)]+)\)', value.lower())
	if cats:
		cat = cats[0]
		if len(cats) > 1:
			print("ERROR: found more than one cat: ", cats)
	return cat.title()

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

def date_remove_time(date):
	return date[:8]

owners = {}
event = None
fp_out = io.open(cal_tmp, 'w')

# first tmp version with ordered events so we can merge them after
with io.open(cal_in, 'r') as fp_in:
	for line in fp_in:
		line = line.rstrip()
		key, value = line.split(":", 1)

		# skip entries with missing value: strange
		if not value:
			continue

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

		# restrict to %Y%m%d format: whole day events
		if (key == DATE_START or key == DATE_END) and 'T' in value:
			event["ORIG" + key] = value
			value = date_remove_time(value)

			# if we had a time, it was during the day: we want to
			# have whole day events so we need to take the next one
			if key == DATE_END:
				value = date_next_day_str(value)

		event[key] = value

		if key == END:
			if value == "VEVENT":
				clean_event(event)

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

# merge events if possible
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
					     is_next_date(prev_event, new_event) and \
					     is_full_day(new_event):
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
