#!/us/bin/python3

#    TestExtractor
#    Copyright (C) 2022  Oleksandr Kolodkin <alexandr.kolodkin@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import subprocess
import shutil
import pandas
from sqlite3 import connect, IntegrityError
from xml.etree import ElementTree
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


@dataclass
class Question(object):
    text: str
    answer: str


@dataclass
class Test(object):
    name: str
    path: Path
    questions: Optional[List[Question]] = None


def extract_apk_resources(input_path: Path, output_path: Path) -> bool:
    print(f'Unpacking: {input_path}')

    # Unpack apk file to the temp directory
    if os.name == 'nt':
        process = subprocess.Popen(f'.\\tools\\apktool.bat d -f -o ".\\temp" {input_path}', shell=True)
    else:
        process = subprocess.Popen(f'./tools/apktool d -f -o ./temp {input_path}', shell=True)

    if process.wait() != 0:
        return False

    # Create directory for the output file
    directory = os.path.dirname(output_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Move the target file to the specified location
    shutil.move('./temp/res/values/arrays.xml', output_path)

    # Remove temp
    shutil.rmtree('temp')

    return True


def make_database(tests: List[Test]):
    print("Creating the database sql file ...")

    sql_header = '\n'.join([
        'DROP TABLE IF EXISTS tests;',
        'DROP TABLE IF EXISTS questions;',
        'DROP TABLE IF EXISTS answers;',
        '',
        'CREATE TABLE tests (',
        '    id INTEGER NOT NULL,',
        '    name TEXT NOT NULL,',
        '    PRIMARY KEY(id)',
        ');',
        '',
        'CREATE TABLE questions (',
        '    id INTEGER NOT NULL,',
        '    text TEXT NOT NULL,',
        '    question_upper TEXT NOT NULL,',
        '    test INTEGER,',
        '    answer INTEGER,',
        '    PRIMARY KEY(id)',
        ');',
        '',
        'CREATE TABLE answers (',
        '    id INTEGER NOT NULL,',
        '    text TEXT UNIQUE,',
        '    PRIMARY KEY(id)',
        ');',
        '',
    ])

    # Read data
    for test in tests:
        print(f'Extract: {test.path}')
        test.questions = list()

        if test.path.suffix == '.xml':
            temp = []
            for item in ElementTree.parse(test.path).getroot().findall(".//*[@name='test']/item"):
                temp.append(item.text)

            for i in range(0, int(len(temp) / 7)):
                question = temp[i * 7 + 0]
                answer = temp[i * 7 + 2]
                test.questions.append(Question(text=str(question).strip(), answer=str(answer).strip()))

        elif test.path.suffix == '.xlsx':
            df = pandas.read_excel(test.path, engine='openpyxl')
            for question, answer in zip(df['Вопрос'], df[1]):
                test.questions.append(Question(text=str(question).strip(), answer=str(answer).strip()))

    # Get answers
    answers = {}
    answer_id = 0
    for test in tests:
        for question in test.questions:
            if question.answer not in answers:
                answers[question.answer] = answer_id
                answer_id += 1

    # Write sql
    with open('tests.sql', 'w', encoding='utf-8') as f:
        f.write(sql_header)

        for test_id, test in enumerate(tests):
            f.write(f"INSERT INTO tests VALUES ({test_id},'{test.name}');\n")
        f.write('\n')

        question_id = 0
        for test_id, test in enumerate(tests):
            for question in test.questions:
                f.write(f"INSERT INTO questions VALUES ({question_id}, '{question.text}', '{question.text.upper()}', ")
                f.write(f"{test_id}, {answers[question.answer]});\n")
                question_id += 1
        f.write('\n')

        for answer_id, text in enumerate(answers):
            f.write(f"INSERT INTO answers VALUES ({answer_id},'{text}');\n")


def make_binary_database(input_path: Path, output_path: Path):
    print("Creating sqlite3 database binary file ...")

    with open(input_path, 'r', encoding='utf-8') as f:
        output_path.unlink(missing_ok=True)

        try:
            sql = f.read()
            con = connect(output_path)
            cur = con.cursor()
            cur.executescript(sql)
            con.commit()

        except IntegrityError as e:
            print(f'Error: {e}')


def main(tests: List[Test]):

    # Extract data from apk's
    for test in tests:
        if test.path.suffix == '.apk':
            if extract_apk_resources(test.path, test.path.with_suffix('.arrays.xml')):
                test.path = test.path.with_suffix('.arrays.xml')
            else:
                return

    # Make the database
    make_database(tests)
    make_binary_database(Path('tests.sql'), Path('tests.sqlite'))

    print("Finished")


if __name__ == '__main__':
    main([
        Test(
            name='Тестирование по НПАОП для РПСС ПАО «Запорожсталь»',
            path=Path("./sources/вопросы ИТР_2019676478357.xlsx")),
        Test(
            name='Тестирование по нарядам-допускам',
            path=Path("./sources/наряд-допуск-2.xlsx")),
        Test(
            name='Тестирование по общим вопросам электробезопасности для работников ПАО «Запорожсталь»',
            path=Path("./sources/elektro.apk")),
        Test(
            name='Новые тесты по электробезопасности',
            path=Path("./sources/тесты-о-эл-без.xlsx")),
    ])
