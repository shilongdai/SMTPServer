import io
import sys
from collections import namedtuple
import socket
import multiprocessing as mtp

# Token types
CHAR = 1
SPEC = 2
SPACE = 3
NEWLINE = 4
EOF = -1
UNREC = -2

# Error Types
COMMAND_UNREC = "500 Syntax error: command unrecognized"
PARAM_ERROR = "501 Syntax error in parameters or arguments"
OUT_OF_ORDER_ERROR = "503 Bad sequence of commands"

# Connection
HOST_NAME = "localhost"
PORT = 9900
MAX_CONN_QUEUE = 5

# OK Types
OK = 250
ENTER_DATA = 354
GREETING = 220
QUIT = 221

OK_MSG = "%d OK" % OK
ENTER_DATA_MSG = "%d Start mail input; end with <CRLF>.<CRLF>" % ENTER_DATA
QUIT_MSG = "%d %s closing connection" % (QUIT, HOST_NAME)

Token = namedtuple("Token", ["type", "spelling"])


def is_ascii(s):
    return all(ord(c) < 128 for c in s)


class TokenScanner:
    SPECIAL = {"<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\""}

    def __init__(self, instream):
        self.instream = instream
        self.current = self.read_token()

    def accept(self, token_type=0, spelling=None):
        acceptable = True
        if token_type != 0 and token_type != self.current.type:
            acceptable = False
        if spelling and spelling != self.current.spelling:
            acceptable = False
        if acceptable:
            self.current = self.read_token()
        return acceptable

    def read_token(self):
        next_char = self.instream.read(1)
        if not next_char:
            return Token(EOF, "\0")
        if next_char == "\t" or next_char == " ":
            return Token(SPACE, next_char)
        if next_char == "\n":
            return Token(NEWLINE, next_char)
        if next_char in TokenScanner.SPECIAL:
            return Token(SPEC, next_char)
        if is_ascii(next_char):
            return Token(CHAR, next_char)
        return Token(UNREC, next_char)


class ParseException(BaseException):

    def __init__(self, error):
        BaseException.__init__(self, error)


class UnrecognizedCommandException(ParseException):

    def __init__(self):
        ParseException.__init__(self, COMMAND_UNREC)


class ParameterErrorException(ParseException):

    def __init__(self):
        ParseException.__init__(self, PARAM_ERROR)


class OutOfOrderException(ParseException):

    def __init__(self):
        ParseException.__init__(self, OUT_OF_ORDER_ERROR)


class MailBox:

    def __init__(self, user, domain):
        self.user = user
        self.domain = domain

    def __str__(self):
        return self.user + "@" + self.domain


class Mail:

    def __init__(self, src, rcpts, text):
        self.src = src
        self.targets = rcpts
        self.text = text


class ClientQuit(BaseException):

    def __init__(self):
        BaseException.__init__(self)


def accept_literal_str(scanner, string):
    for s in string:
        if not scanner.accept(spelling=s):
            return False
    return True


def parse_mail_from_cmd(scanner):
    try:
        if not accept_literal_str(scanner, "MAIL"):
            raise UnrecognizedCommandException()
        parse_whitespace(scanner)
        if not accept_literal_str(scanner, "FROM:"):
            raise UnrecognizedCommandException()
    except ParseException:
        raise UnrecognizedCommandException()

    parse_nullspace(scanner)
    path = parse_path(scanner)
    parse_nullspace(scanner)
    if not scanner.accept(NEWLINE):
        raise ParameterErrorException()
    return path


def parse_whitespace(scanner):
    if not scanner.accept(SPACE):
        raise ParameterErrorException()
    while scanner.current.type == SPACE:
        scanner.accept(SPACE)


def parse_nullspace(scanner):
    if scanner.current.type == SPACE:
        parse_whitespace(scanner)


def parse_path(scanner):
    if not scanner.accept(SPEC, "<"):
        raise ParameterErrorException()
    mail_box = parse_mailbox(scanner)
    if not scanner.accept(SPEC, ">"):
        raise ParameterErrorException()
    return mail_box


def parse_mailbox(scanner):
    user = parse_string(scanner)
    if not scanner.accept(SPEC, "@"):
        raise ParameterErrorException()
    domain = parse_domain(scanner)
    return MailBox(user, domain)


def parse_string(scanner):
    result = [scanner.current.spelling]
    if not scanner.accept(CHAR):
        raise ParameterErrorException()
    while scanner.current.type == CHAR:
        result.append(scanner.current.spelling)
        scanner.accept(CHAR)
    return "".join(result)


def parse_domain(scanner):
    result = [parse_element(scanner)]
    if scanner.current.type == SPEC and scanner.current.spelling == ".":
        result.append(scanner.current.spelling)
        scanner.accept(SPEC, ".")
        result.append(parse_domain(scanner))
    return "".join(result)


def accept_letter(scanner):
    result = None
    if scanner.current.type == CHAR and scanner.current.spelling.isalpha():
        result = scanner.current.spelling
        scanner.accept(CHAR, scanner.current.spelling)
    return result


def parse_element(scanner):
    result = []
    letter = accept_letter(scanner)
    if not letter:
        raise ParameterErrorException()
    result.append(letter)

    if not scanner.current.type == CHAR:
        return "".join(result)
    if scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        result.append(parse_letter_digit_string(scanner))
    return "".join(result)


def parse_letter_digit_string(scanner):
    result = [parse_letter_digit(scanner)]

    if not scanner.current.type == CHAR:
        return "".join(result)
    while scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        result.append(parse_letter_digit(scanner))
    return "".join(result)


def parse_letter_digit(scanner):
    if scanner.current.type != CHAR:
        raise ParameterErrorException()
    if scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        result = scanner.current.spelling
        scanner.accept(CHAR, scanner.current.spelling)
        return result
    else:
        raise ParameterErrorException()


def parse_rcpt_to(scanner):
    try:
        if not accept_literal_str(scanner, "RCPT"):
            raise UnrecognizedCommandException()
        parse_whitespace(scanner)
        if not accept_literal_str(scanner, "TO:"):
            raise UnrecognizedCommandException()
    except ParseException:
        raise UnrecognizedCommandException()

    parse_nullspace(scanner)
    path = parse_path(scanner)
    parse_nullspace(scanner)
    if not scanner.accept(NEWLINE):
        raise ParameterErrorException()
    return path


def parse_data_cmd(scanner):
    if not accept_literal_str(scanner, "DATA"):
        raise UnrecognizedCommandException()
    parse_nullspace(scanner)
    if not scanner.accept(NEWLINE):
        raise ParameterErrorException()


def parse_helo_cmd(scanner):
    if not accept_literal_str(scanner, "HELO"):
        raise UnrecognizedCommandException()
    parse_whitespace(scanner)
    domain = parse_domain(scanner)
    parse_nullspace(scanner)
    if not scanner.accept(NEWLINE):
        raise ParameterErrorException()
    return domain


def parse_data_txt(server_in, server_out):
    result = []
    for line in server_in:
        if line.rstrip() == ".":
            return "".join(result)
        result.append(line)


def try_parse(line, expected, funcs):
    if line.strip() == "":
        raise UnrecognizedCommandException()
    stream = io.StringIO(line)
    tok_scanner = TokenScanner(stream)
    if tok_scanner.current.spelling[0] not in funcs:
        raise UnrecognizedCommandException()
    f = funcs[tok_scanner.current.spelling[0]]
    if f:
        try:
            parsed = f(tok_scanner)
            if f not in expected:
                raise OutOfOrderException()
            return f, parsed
        except ParameterErrorException:
            if f not in expected:
                raise OutOfOrderException()
            else:
                raise
    else:
        raise UnrecognizedCommandException()


PARSERS = {"M": parse_mail_from_cmd, "R": parse_rcpt_to, "D": parse_data_cmd, "H": parse_helo_cmd}


def handle_quit(server_out):
    print(QUIT_MSG, file=server_out, flush=True)


def read_next_line(server_in, server_out):
    try:
        line = next(server_in)
        if line.strip() == "QUIT":
            handle_quit(server_out)
            raise ClientQuit()
        return line
    except StopIteration:
        exit(0)


def accept_rcpt_to(server_in, server_out):
    rcpts = []
    rcpt_line = read_next_line(server_in, server_out)
    f, rcpt_addr = try_parse(rcpt_line, [parse_rcpt_to], PARSERS)
    while f == parse_rcpt_to:
        print(OK_MSG, file=server_out, flush=True)
        rcpts.append(rcpt_addr)
        rcpt_line = read_next_line(server_in, server_out)
        f, rcpt_addr = try_parse(rcpt_line, [parse_rcpt_to, parse_data_cmd], PARSERS)
    return rcpts


def accept_data_entry(server_in, server_out):
    print(ENTER_DATA_MSG, file=server_out, flush=True)
    return parse_data_txt(server_in, server_out)


def accept_mail_from(server_in, server_out):
    mail_from = read_next_line(server_in, server_out)
    f, from_addr = try_parse(mail_from, [parse_mail_from_cmd], PARSERS)
    print(OK_MSG, file=server_out, flush=True)
    rcpts = accept_rcpt_to(server_in, server_out)
    text = accept_data_entry(server_in, server_out)
    print(OK_MSG, file=server_out, flush=True)
    return Mail(from_addr, rcpts, text)


def mail_to_string(mail):
    result = []
    result.append("From: ")
    result.append("<")
    result.append(str(mail.src))
    result.append(">\n")
    for rcpt in mail.targets:
        result.append("To: ")
        result.append("<")
        result.append(str(rcpt))
        result.append(">\n")
    result.append(mail.text)
    return "".join(result)


def accept_helo(server_in, server_out):
    helo = read_next_line(server_in, server_out)
    f, helo_msg = try_parse(helo, (parse_helo_cmd,), PARSERS)
    print("%d %s pleased to meet you" % (OK, helo_msg), file=server_out, flush=True)


def process_request(client_conn):
    try:
        with client_conn.makefile(mode="r", newline="\n") as server_in, client_conn.makefile(mode="w") as server_out:
            helo_accepted = False
            print("%d %s" % (GREETING, HOST_NAME), file=server_out, flush=True)
            while not helo_accepted:
                try:
                    accept_helo(server_in, server_out)
                    helo_accepted = True
                except ParseException as e:
                    print(e.args[0], file=server_out, flush=True)
            while True:
                try:
                    mail = accept_mail_from(server_in, server_out)
                    mail_to_save = mail_to_string(mail)
                    file_names = set([box.domain for box in mail.targets])
                    for file_name in file_names:
                        with open("forward/" + file_name, "a") as file:
                            file.write(mail_to_save)
                except ParseException as e:
                    print(e.args[0], file=server_out, flush=True)
    except ClientQuit:
        return
    except Exception as final_error:
        print(final_error)
    finally:
        client.shutdown(socket.SHUT_RDWR)
        client_conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Please specify only the port number")
        exit(0)
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except Exception as e:
        print(e)
        exit(0)
    try:
        PORT = int(sys.argv[1])
        server_socket.bind(("", PORT))
        server_socket.listen(MAX_CONN_QUEUE)

        while True:
            client, addr = server_socket.accept()
            process = mtp.Process(target=process_request, args=(client,))
            process.start()

    except Exception as e:
        print(e)
    finally:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.close()

