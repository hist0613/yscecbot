# -*- encoding:utf-8 -*-
from __future__ import absolute_import

import os
import pickle
from urllib.parse import urlparse, parse_qs
import re

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

from settings import *

def main():
    try:
        # 저장된 세션이 존재하는 경우
        with open("user/{user_id}.session".format(user_id=STUDENT_ID), 'rb') as fp:
            session = pickle.load(fp)

        # 저장된 세션이 존재하지만 로그인에 실패한 경우
        if session.get("http://yscec.yonsei.ac.kr/my/").url != "http://yscec.yonsei.ac.kr/my/":
            print("NotValidSession")
            raise Exception("NotValidSession")

    except:
        # 저장된 세션이 존재하지 않는 경우 로그인 처리 후 세션 저장
        driver = webdriver.Firefox()
        driver.get("http://yscec.yonsei.ac.kr/login/index.php")
        username_input = WebDriverWait(driver, 5).until(
            expected_conditions.presence_of_element_located((By.ID, "username"))
        )
        username_input.clear()
        username_input.send_keys(STUDENT_ID)
        password_input = WebDriverWait(driver, 5).until(
            expected_conditions.presence_of_element_located((By.ID, "password"))
        )
        password_input.clear()
        password_input.send_keys(STUDENT_PW)
        password_input.send_keys(Keys.RETURN)

        # http://yscec.yonsei.ac.kr/my/ 로 이동하지 않았다면 로그인이 실패한 상황
        if driver.current_url != "http://yscec.yonsei.ac.kr/my/":
            print("Login Failed!")
            return

        # 속도 향상을 위해 selenium은 세션을 얻는 것 까지만 담당하고, 이후로는 requests 사용
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        driver.close()

        with open("user/{user_id}.session".format(user_id=STUDENT_ID), 'wb') as fp:
            pickle.dump(session, fp)

    # 나의 YSCEC 처리
    my_page = BeautifulSoup(session.get("http://yscec.yonsei.ac.kr/my/").text, "html.parser")
    for course in my_page.find_all('div', 'course_title'):
        course_link = course.a['href']
        course_title = course.a.text
        course_id = int(parse_qs(urlparse(course_link).query)['id'][0])

        print('\n' + course_title)

        forums_link = "http://yscec.yonsei.ac.kr/mod/jinotechboard/index.php?id={course_id}".format(course_id=course_id)
        forums_page = BeautifulSoup(session.get(forums_link).text, "html.parser")
        for forum in forums_page.tbody.find_all('tr'):
            forum_id = int(re.search(r'\d+', forum.a['href']).group())
            FORUM_BASE_URL = "http://yscec.yonsei.ac.kr/mod/jinotechboard/"
            forum_link = FORUM_BASE_URL + forum.a['href']
            forum_page = BeautifulSoup(session.get(forum_link).text, "html.parser")

            posts = forum_page.find_all('div', 'thread-style')[0]
            posts = [post for post in posts.find_all('li') if post.get('class', [''])[0] != 'isnotice']
            for post in posts:
                # post_title = post.find_all('h1', 'thread-post-title')[0].a.text
                post_id = post.find_all('h1', 'thread-post-title')[0].a['onclick']
                post_id = int(re.search(r'\d+', post_id).group())

                post_page = session.post("http://yscec.yonsei.ac.kr/mod/jinotechboard/content.php",
                            params={'b': forum_id, 'contentId': post_id, 'page': 1, 'perpage': 10, 'boardform': 1}).text
                post_page = BeautifulSoup(post_page, "html.parser")

                post_title = post_page.find_all('span', 'detail-title')[0].text
                post_date = post_page.find_all('span', 'detail-date')[0].text
                post_date = post_date.split(post_page.find_all('span', 'detail-date')[0].a.text)[-1]
                post_contents = post_page.find_all('div', 'detail-contents')[0].text
                # print("제목: {}".format(post_title))
                # print("날짜: {}".format(post_date))
                # print("내용: {}".format(post_contents[:100]))

                # post_date에 "씀"이 들어가있다면, 현재 시간(datetime.datetime.now)를 사용하는게 좋을 듯
                # post_date(string)을 datetime으로 바꿔야하는데, 앞에 '-'를 지워버리고, 적당히 바꾸면 될 듯

        recourses_link = "http://yscec.yonsei.ac.kr/course/resources.php?id={course_id}".format(course_id=course_id)




    # 세션은 기본적으로 저장해놓지만 저장된 세션이 계속 사용가능한지, 즉 로그인 성공인지 실패인지 다른 페이지에서도 확인할 수 있어야함
    #  - 로그인 실패인 경우 당사자에게 자동으로 slack message가 갈 수 있어야함
    # 새로운 공지사항, 강의자료, 과제 알림
    #  - Forum(general), Resources 이 2가지를 잘 살펴보며 될 듯
    # 과제 제출 남은 시간 알림 (일주일, 3일, 1일, 12시간, 6시간, 3시간, 1시간, 10분 단위)
    #  - 이건 시간을 계속 체크하기 보다는 celery나 cron을 이용해서 처리하는게 좋을 듯
    # 쪽지도 알림해줬으면 좋겠음. 쪽지 체크하는거 존나 귀찮 ㅅㅂ
    # Grades(점수)에 추가된 내용도 자동으로 알림해주면 좋을 듯

if __name__ == '__main__':
    main()
