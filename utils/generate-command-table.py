#!/usr/bin/env python

import os
import glob
import json

# Note: This script should be run from the src/ dir: ../utils/generate-command-table.py

class KeySpec(object):
    def __init__(self, spec):
        self.spec = spec

    def code(self):
        def _flags_code():
            s = ""
            for flag in self.spec.get("flags", []):
                s += "%s " % flag
            return s[:-1]

        def _begin_search_code():
            if self.spec["begin_search"].get("index"):
                return "KSPEC_BS_INDEX,.bs.index={%d}" % (
                    self.spec["begin_search"]["index"]["pos"]
                )
            elif self.spec["begin_search"].get("keyword"):
                return "KSPEC_BS_INDEX,.bs.keyword={\"%s\",%d}" % (
                    self.spec["begin_search"]["keyword"]["keyword"],
                    self.spec["begin_search"]["keyword"]["startfrom"],
                )
            else:
                print("Invalid begin_search! value=%s" % self.spec["begin_search"])
                exit(1)

        def find_keys_code():
            if self.spec["find_keys"].get("range"):
                return "KSPEC_FK_RANGE,.fk.range={%d,%d,%d}" % (
                    self.spec["find_keys"]["range"]["lastkey"],
                    self.spec["find_keys"]["range"]["step"],
                    self.spec["find_keys"]["range"]["limit"]
                )
            elif self.spec["find_keys"].get("keynum"):
                return "KSPEC_FK_RANGE,.fk.keynum={%d,%d,%d}" % (
                    self.spec["find_keys"]["keynum"]["keynumidx"],
                    self.spec["find_keys"]["keynum"]["firstkey"],
                    self.spec["find_keys"]["keynum"]["step"]
                )
            else:
                print("Invalid find_keys! value=%s" % self.spec["find_keys"])
                exit(1)

        return "\"%s\",%s,%s" % (
            _flags_code(),
            _begin_search_code(),
            find_keys_code()
        )


class Command(object):
    def __init__(self, name, desc):
        self.name = name.upper()
        self.desc = desc
        self.subcommands = []
        self.group = self.desc["group"]

    def code(self):
        """
        "SET",setCommand,-3,"write use-memory @string",{{"write",KSPEC_BS_INDEX,.bs.index={1},KSPEC_FK_RANGE,.fk.range={0,1,0}}}
        """
        def _flags_code():
            s = ""
            for flag in self.desc.get("command_flags", []):
                s += "%s " % flag
            for cat in self.desc.get("acl_categories", []):
                s += "@%s " % cat
            return s[:-1]

        def _key_specs_code():
            s = ""
            for spec in self.desc.get("key_specs", []):
                s += "{%s}," % KeySpec(spec).code()
            return s[:-1]

        flags = _flags_code()
        s = "\"%s\",%s,%d,\"%s\"," % (
            self.name,
            self.desc.get("function", "NULL"),
            self.desc["arity"],
            flags
        )

        specs = _key_specs_code()
        if specs:
            s += "{%s}," % specs

        if self.desc.get("get_keys_function"):
            s += "%s," % self.desc["get_keys_function"]

        return s[:-1]

    def __str__(self):
        return self.code()


class ContainerCommand(Command):
    def __init__(self, name, desc):
        super(ContainerCommand, self).__init__(name, desc)
        self.subcommands = []

    def subcommands_table_name(self):
        assert self.subcommands
        return "%s_Subcommands" % self.name

    def code(self):
        return super(ContainerCommand, self).code() + ",.subcommands=%s" % self.subcommands_table_name()


class Subcommand(Command):
    def __init__(self, name, desc):
        super(Subcommand, self).__init__(name, desc)
        self.container_name = self.desc["container"].upper()


subcommands = {}  # container_name -> dict(subcommand_name -> Subcommand)
commands = {}  # command_name -> Command
container_commands = {}  # container_command_name -> ContainerCommand


def create_command(name, desc):
    if desc.get("container"):
        cmd = Subcommand(name, desc)
        subcommands.setdefault(desc["container"].upper(), {})[name] = cmd
    else:
        if desc.get("subcommands"):
            cmd = ContainerCommand(name, desc)
            container_commands[name.upper()] = cmd
        else:
            cmd = Command(name.upper(), desc)
        commands[name.upper()] = cmd


# Create all command objects
print("Processing json files...")
for filename in glob.glob('commands/*.json'):
    print(filename)
    with open(filename,"r") as f:
        d = json.load(f)
        for name, desc in d.items():
            create_command(name, desc)

# Link subcommands to containers
print("Linking container command to subcommands...")
for container in container_commands.values():
    for subcommand in subcommands[container.name].values():
        container.subcommands.append(subcommand)


def write_command_table(f, container_name, table_name, command_list):
    f.write("/* %s command table */\n" % (container_name or "Main"))
    f.write("struct redisCommand %s[] = {\n" % table_name)
    curr_group = None
    for command in command_list:
        if container_name is None and curr_group != command.group:
            curr_group = command.group
            f.write("    /* %s */\n" % curr_group)
        f.write("    {%s},\n" % command)
    f.write("}\n\n")


print("Generating commands.c...")
with open("commands.c","w") as f:
    f.write("/* Automatically generated by %s, do not edit. */\n\n" % os.path.basename(__file__))
    # Write all subcommand tables
    for container in sorted(container_commands.values(), key=lambda cmd: (cmd.group, cmd.name)):
        write_command_table(f, container.name, container.subcommands_table_name(), sorted(container.subcommands, key=lambda cmd: cmd.name))
    # Write main command table
    write_command_table(f, None, "redisCommandTable", sorted(commands.values(), key=lambda cmd: (cmd.group, cmd.name)))

print("All done, exiting.")

