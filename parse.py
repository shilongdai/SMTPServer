import io
import sys
from collections import namedtuple

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

# OK Types
OK = "250 OK"
ENTER_DATA = "354 Start mail input; end with <CRLF>.<CRLF>"

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


class Mail:

    def __init__(self, src, rcpts, text):
        self.src = src
        self.targets = rcpts
        self.text = text


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
    return user + "@" + domain


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


def parse_data_txt():
    result = []
    for line in sys.stdin:
        print(line, end="")
        if line.rstrip() == ".":
            return "".join(result)
        result.append(line)


def try_parse(line, expected, funcs):
    if line.strip() == "":
        raise UnrecognizedCommandException()
    stream = io.StringIO(line)
    tok_scanner = TokenScanner(stream)
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


PARSERS = {"M": parse_mail_from_cmd, "R": parse_rcpt_to, "D": parse_data_cmd}


def read_next_line():
    try:
        line = next(sys.stdin)
        print(line, end="")
        return line
    except StopIteration:
        exit(0)


def accept_rcpt_to():
    rcpts = []
    rcpt_line = read_next_line()
    f, rcpt_addr = try_parse(rcpt_line, [parse_rcpt_to], PARSERS)
    while f == parse_rcpt_to:
        print(OK)
        rcpts.append(rcpt_addr)
        rcpt_line = read_next_line()
        f, rcpt_addr = try_parse(rcpt_line, [parse_rcpt_to, parse_data_cmd], PARSERS)
    return rcpts


def accept_data_entry():
    print(ENTER_DATA)
    return parse_data_txt()


def accept_mail_from():
    mail_from = read_next_line()
    f, from_addr = try_parse(mail_from, [parse_mail_from_cmd], PARSERS)
    print(OK)
    rcpts = accept_rcpt_to()
    text = accept_data_entry()
    print(OK)
    return Mail(from_addr, rcpts, text)


def mail_to_string(mail):
    result = []
    result.append("From: ")
    result.append("<")
    result.append(mail.src)
    result.append(">\n")
    for rcpt in mail.targets:
        result.append("To: ")
        result.append("<")
        result.append(rcpt)
        result.append(">\n")
    result.append(mail.text)
    return "".join(result)


if __name__ == "__main__":
    while True:
        try:
            mail = accept_mail_from()
            mail_to_save = mail_to_string(mail)
            for file_name in mail.targets:
                with open("forward/" + file_name, "a") as file:
                    file.write(mail_to_save)
        except ParseException as e:
            print(e.args[0])
