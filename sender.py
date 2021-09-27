import io
import sys

from parse import ENTER_DATA
from parse import Mail
from parse import OK
from parse import OutOfOrderException
from parse import ParseException
from parse import UnrecognizedCommandException
from parse import accept_literal_str
from parse import parse_path
from parse import try_parse


def parse_from_header(scanner):
    if not accept_literal_str(scanner, "From: "):
        raise UnrecognizedCommandException()
    return parse_path(scanner)


def parse_to_header(scanner):
    if not accept_literal_str(scanner, "To: "):
        raise UnrecognizedCommandException()
    return parse_path(scanner)


PARSERS = {"F": parse_from_header, "T": parse_to_header}


def read_forward_file(file):
    try:
        next_line = file.readline()
        return next_line
    except IOError:
        exit(0)


def read_from_line(file):
    from_line = read_forward_file(file)
    if len(from_line) == 0:
        return None
    f, parsed = try_parse(from_line, [parse_from_header], PARSERS)
    return parsed


def read_to_lines(file):
    result = []
    to_line = read_forward_file(file)
    f, parsed = try_parse(to_line, [parse_to_header], PARSERS)
    result.append(parsed)
    while True:
        position = file.seek(0, io.SEEK_CUR)
        to_line = read_forward_file(file)
        try:
            f, parsed = try_parse(to_line, [parse_to_header], PARSERS)
            result.append(parsed)
        except (UnrecognizedCommandException, OutOfOrderException):
            file.seek(position)
            break
    return result


def read_data(file):
    result = []
    while True:
        position = file.seek(0, io.SEEK_CUR)
        data_line = read_forward_file(file)
        if len(data_line) == 0:
            break
        try:
            try_parse(data_line, [parse_from_header], PARSERS)
            file.seek(position)
            break
        except ParseException:
            result.append(data_line)
    return "".join(result)


def read_mail(file):
    from_header = read_from_line(file)
    if not from_header:
        return None
    to_headers = read_to_lines(file)
    data = read_data(file)
    return Mail(from_header, to_headers, data)


def read_server_output(stream):
    try:
        output = next(stream)
        print(output, file=sys.stderr, end="")
        return output
    except (IOError, StopIteration):
        exit(0)


def match_code(resp, code):
    if len(resp) < 3:
        return False
    code_str = resp[:3]
    if not code_str.isdigit():
        return False
    code_int = int(code_str)
    return code == code_int


def exit_sequence(server_out):
    print("QUIT", file=server_out)
    exit(0)


def handle_mail_from(from_addr, server_in, server_out):
    print("MAIL FROM: <%s>" % from_addr, file=server_out)
    resp = read_server_output(server_in)
    if not match_code(resp, OK):
        exit_sequence(server_out)


def handle_mail_to(to_addrs, server_in, server_out):
    for addr in to_addrs:
        print("RCPT TO: <%s>" % addr, file=server_out)
        resp = read_server_output(server_in)
        if not match_code(resp, OK):
            exit_sequence(server_out)


def handle_data(data, server_in, server_out):
    print("DATA", file=server_out)
    resp = read_server_output(server_in)
    if not match_code(resp, ENTER_DATA):
        exit_sequence(server_out)
    print(data, file=server_out, end="")
    if data[-1] == "\n":
        print(".")
    else:
        print("\n.")
    resp = read_server_output(server_in)
    if not match_code(resp, OK):
        exit_sequence(server_out)


def process_mails(path, server_in, server_out):
    with open(path, "r") as file:
        while True:
            try:
                next_mail = read_mail(file)
                if not next_mail:
                    exit_sequence(server_out)
            except (ParseException, IOError):
                exit_sequence(server_out)
            handle_mail_from(next_mail.src, server_in, server_out)
            handle_mail_to(next_mail.targets, server_in, server_out)
            handle_data(next_mail.text, server_in, server_out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        exit(0)
    process_mails(sys.argv[1], sys.stdin, sys.stdout)
