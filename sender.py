import io
import sys
import socket

import parse
from parse import ENTER_DATA
from parse import Mail
from parse import OK
from parse import GREETING
from parse import ParseException
from parse import TokenScanner
from parse import parse_mailbox


INCORRECT_FROM_PATH = "Incorrect from path, please try again"
INCORRECT_TO_PATH = "Incorrect to path, please try again"
UNCLEAN_EXIT = "Failed to gracefully quit from server"
UNEXPECTED_CONNECTION_CLOSE = "Server closed connection unexpectedly"
FAILED_TO_ENTER_MAIL_FROM = "Server did not accept source address"
FAILED_TO_ENTER_RCPTS = "Server did not accept recipients"
SERVER_NOT_READY_FOR_DATA = "Server did not want to accept message data"
SERVER_REJECT_DATA = "Server rejected message data"
INVALID_SERVER_GREETING = "Server failed to greet properly"


CONNECTION_TIMEOUT = 5


def try_parse_mailbox(line):
    stream = io.StringIO(line)
    tok_scanner = TokenScanner(stream)
    return parse_mailbox(tok_scanner)


def read_from_line(file):
    parsed = None
    while parsed is None:
        print("From:")
        from_line = next(file)
        try:
            parsed = try_parse_mailbox(from_line)
        except ParseException:
            print(INCORRECT_FROM_PATH)
    return parsed


def read_to_lines(file):
    result = []
    while len(result) == 0:
        print("To:")
        to_combo = next(file)
        separate_tos = [s.strip() for s in to_combo.split(",")]
        try:
            for to_line in separate_tos:
                parsed = try_parse_mailbox(to_line)
                result.append(parsed)
        except ParseException:
            print(INCORRECT_TO_PATH)
            result = []
    return result


def read_data(file):
    print("Subject:")
    result = ["Subject: %s" % next(file), "\n"]
    print("Message:")
    while True:
        data_line = next(file)
        if data_line == ".\n":
            break
        result.append(data_line)
    return "".join(result)


def read_mail(file):
    from_header = read_from_line(file)
    to_headers = read_to_lines(file)
    data = read_data(file)
    header = ["From: ", "<%s>\n" % from_header, "To: "]
    for to in to_headers:
        header.append("<%s>" % str(to))
        header.append(", ")
    del header[-1]
    header.append("\n")
    data = "".join(header) + data
    return Mail(from_header, to_headers, data)


def read_server_output(stream):
    try:
        output = next(stream)
        return output
    except (IOError, StopIteration):
        print(UNEXPECTED_CONNECTION_CLOSE)
        exit(0)


def match_code(resp, code):
    if len(resp) < 3:
        return False
    resp = resp.strip()
    code_str = resp[:3]
    if not code_str.isdigit():
        return False
    if resp == code_str:
        return False
    if resp[3] != " " and resp[3] != "\t":
        return False
    if len(resp[4:]) == 0 or not resp[4:].isascii():
        return False
    code_int = int(code_str)
    return code == code_int


def exit_sequence(server_in, server_out):
    print("QUIT", file=server_out, flush=True)
    goodbye = read_server_output(server_in)
    if match_code(goodbye, parse.QUIT):
        exit(0)
    else:
        print(UNCLEAN_EXIT)
        exit(0)


def handle_mail_from(from_addr, server_in, server_out):
    print("MAIL FROM: <%s>" % from_addr, file=server_out, flush=True)
    resp = read_server_output(server_in)
    if not match_code(resp, OK):
        print(FAILED_TO_ENTER_MAIL_FROM)
        exit_sequence(server_in, server_out)


def handle_mail_to(to_addrs, server_in, server_out):
    for addr in to_addrs:
        print("RCPT TO: <%s>" % str(addr), file=server_out, flush=True)
        resp = read_server_output(server_in)
        if not match_code(resp, OK):
            print(FAILED_TO_ENTER_RCPTS)
            exit_sequence(server_in, server_out)


def handle_data(data, server_in, server_out):
    print("DATA", file=server_out, flush=True)
    resp = read_server_output(server_in)
    if not match_code(resp, ENTER_DATA):
        print(SERVER_NOT_READY_FOR_DATA)
        exit_sequence(server_in, server_out)
    print(data, file=server_out, end="", flush=True)
    if len(data) == 0:
        print(".", file=server_out, flush=True)
    elif data[-1] == "\n":
        print(".", file=server_out, flush=True)
    else:
        print("\n.", file=server_out, flush=True)
    resp = read_server_output(server_in)
    if not match_code(resp, OK):
        print(SERVER_REJECT_DATA)
        exit_sequence(server_in, server_out)


def greeting_sequence(server_in, server_out):
    domain = get_my_domain()
    server_greeting = read_server_output(server_in)
    if not match_code(server_greeting, GREETING):
        print(INVALID_SERVER_GREETING)
        exit_sequence(server_in, server_out)
    print("HELO %s" % domain, file=server_out, flush=True)
    server_resp = read_server_output(server_in)
    if not match_code(server_resp, OK):
        print(INVALID_SERVER_GREETING)
        exit_sequence(server_in, server_out)


def get_my_domain():
    fqdn = socket.getfqdn()
    separated = fqdn.split(".")
    if len(separated) == 1:
        return separated[0]
    else:
        return ".".join(separated[1:])


def process_mails(host, port):
    try:
        next_mail = read_mail(sys.stdin)
        if not next_mail:
            return
    except StopIteration:
        return
    except IOError as e:
        print(e)
        return
    try:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.settimeout(CONNECTION_TIMEOUT)
        client_sock.connect((host, port))
    except OSError as e:
        print(e)
        return
    try:
        with client_sock.makefile(mode="r", newline="\n") as server_in, client_sock.makefile(mode="w") as server_out:
            greeting_sequence(server_in, server_out)
            handle_mail_from(next_mail.src, server_in, server_out)
            handle_mail_to(next_mail.targets, server_in, server_out)
            handle_data(next_mail.text, server_in, server_out)
            exit_sequence(server_in, server_out)
    finally:
        client_sock.shutdown(socket.SHUT_RDWR)
        client_sock.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Please input mail server and port")
        exit(0)
    try:
        port = int(sys.argv[2])
        process_mails(sys.argv[1], port)
    except Exception as e:
        print(e)
