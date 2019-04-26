#+
# Useful definitions across my Nagios plugins. Currently
# this just includes maintenance of persistent state, so plugins
# can report rates of change in selected counters. I’m surprised
# that Nagios itself makes no provision for such a thing.
#
# Copyright 2019 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY <https://creativecommons.org/licenses/by/4.0/>.
#-

import os
import time
import apsw as sqlite

#+
# Common management of persistent data
#-

persistent_basedir = os.path.join(os.path.expanduser("~nagios"), "ldo_nagios")
  # nagios user has a valid home dir, might as well use it
  # (Even though nagios server does not define $HOME)

class PersistentStats :
    "maintains an SQLite database in a common location that I can use" \
    " for storing persistent counters in-between invocations of a plugin" \
    " that reports incremental changes in those counters."

    def __init__(self, prefix) :
        os.makedirs(persistent_basedir, mode = 0o700, exist_ok = True)
        self.conn = sqlite.Connection \
          (
            os.path.join(persistent_basedir, "stats.db"),
            sqlite.SQLITE_OPEN_CREATE | sqlite.SQLITE_OPEN_READWRITE
          )
        cu = self.conn.cursor()
        cu.execute("begin transaction")
        try :
            cu.execute("select count(*) from vars")
        except sqlite.SQLError :
            inited = False
        else :
            inited = True
        #end try
        if not inited :
            cu.execute \
              (
                "create table vars\n"
                "  (\n"
                "    name varchar primary key not null,\n"
                "    value real not null,\n"
                "    last_modified real not null /* seconds since 01-Jan-1970 00:00:00Z */\n"
                "  )\n"
              )
        #end if
        cu.execute("end transaction")
        self.prefix = prefix
        self.startup_time = time.time() - float(open("/proc/uptime", "r").read().strip().split()[0])
    #end __init__

    def get_and_update(self, newvals, now) :
        "given newvals, a dictionary of new name-value pairs, updates those values" \
        " in the database after creating a dictionary for returning 4-tuples containing" \
        " their previous values and update times (None if not previously present) along" \
        " with changes in those values and times. now is the current time to be stored" \
        " with the updated values."
        result = {}
        if len(newvals) != 0 :
            names_to_keys = dict((n, "%s.%s" % (self.prefix, n)) for n in newvals)
            keys_to_names = dict((names_to_keys[n], n) for n in newvals)
            cu = self.conn.cursor()
            cu.execute("begin transaction")
            rowiter = cu.execute \
              (
                    "select name, value, last_modified from vars where name in (%s)"
                %
                    ", ".join(sqlite.format_sql_value(k) for k in keys_to_names)
              )
            for n in newvals :
                result[n] = (None, None, None, None)
            #end for
            for row in rowiter :
                # ignore entries older than last reboot
                if row[2] >= self.startup_time :
                    name = keys_to_names[row[0]]
                    result[name] = (row[1], row[2], newvals[name] - row[1], now - row[2])
                #end if
            #end for
            for name, value in newvals.items() :
                cu.execute \
                  (
                    "insert or replace into vars(name, value, last_modified) values (?, ?, ?)",
                    (names_to_keys[name], value, now)
                  )
            #end for
            cu.execute("end transaction")
        #end if
        return \
            result
    #end get_and_update

#end PersistentStats
