import ntpath
import sys
from glob import glob
from typing import Tuple
import json
from ics.grammar.parse import ContentLine
import requests
from bs4 import BeautifulSoup
from requests.structures import CaseInsensitiveDict
from ics import Calendar, Event
import re
from datetime import date

ICS_FILE_NAME = "china.holiday.ics"
JSON_FILE_NAME = "china.holiday.json"
ICS_CURRENT_YEARS_LIST_NAME = "ICSCURRENTYEARS"


def get(url: str):
    headers = CaseInsensitiveDict()
    headers[
        "User-Agent"
    ] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36"
    headers["Referer"] = "http://www.gov.cn/"
    resp = requests.get(url, headers=headers)
    return resp


def get_gov_cn_holiday_resp():
    """获取政府信息公布平台 关于节假日返回的数据

    Returns:
        [type]: 节假日列表 resp
    """
    url = "http://xxgk.www.gov.cn/search-zhengce/?mode=smart&sort=relevant&page_index=1&page_size=10&title=%E8%8A%82%E5%81%87%E6%97%A5&_=1641913082416"
    resp = get(url)
    if resp.status_code != 200:
        sys.exit("request info error")
    return resp.json()["data"]


def get_holiday_cache():
    """获取当前在本地存储的缓存节假日文件

    Returns:
        [list<str>]: 文件名称集合
    """
    return [ntpath.basename(file).split(".")[0] for file in glob("./holidays/*.html")]


def chunks(lst, n):
    """将 list 按照大小 分组"""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class Holiday:
    """节假日对象"""

    holiday_name: str
    """节假日名称"""
    holiday_start_date: date
    """节假日开始日期"""
    holiday_end_date: date
    """节假日结束日期"""
    compensatory: list
    """节假日补休日期集合"""

    def __init__(
        self,
        holiday_name: str,
        holiday_start_date: date,
        holiday_end_date: date,
        compensatory: list,
    ):
        self.holiday_name = holiday_name
        self.holiday_start_date = holiday_start_date
        self.holiday_end_date = holiday_end_date
        self.compensatory = compensatory

    # def default(self, o):
    #     return o.__dict__

    def __dict__(self):
        return {
            "holiday_name": self.holiday_name,
            "holiday_start_date": self.holiday_start_date,
            "holiday_end_date": self.holiday_end_date,
            "compensatory": self.compensatory,
        }

    # def toJson(self):
    #     return json.dumps(self.__dict__())

    def __repr__(self):
        return self.__str__()

    def __str__(self) -> str:
        return f"{self.holiday_name}: {self.holiday_start_date} - {self.holiday_end_date} , {None if self.compensatory is None else [str(c) for c in self.compensatory]}"


def parse_single_line(year: int, line: str):
    """根据传入的行，通过正则表达式匹配节假日以及补休日期

    Args:
        year (int): 年份
        line (str): 当前需要检查的行

    Returns:
        [type]: 如果匹配到就返回 Holiday 否则则返回None
    """
    name = None
    start_date = None
    end_date = None
    compensatory = None

    res = re.findall(r"^(.*)：(\d+)月(\d+)日至(\d+)日放假", line)
    if len(res) > 0:
        res = list(res[0])
        name = res[0]
        start_date = date(year, int(res[1]), int(res[2]))
        end_date = date(year, int(res[1]), int(res[3]))

    res = re.findall(r"^(.*)：(\d+)月(\d+)日至(\d+)月(\d+)日放假", line)
    if len(res) > 0:
        res = list(res[0])
        name = res[0]
        start_date = date(year, int(res[1]), int(res[2]))
        end_date = date(year, int(res[3]), int(res[4]))

    res = re.findall(r"(\d+)月(\d+)日（星期.?）", line)
    if len(res) > 0:
        compensatory = []
        for md in list(chunks(res, 2)):
            for r in md:
                compensatory.append(date(year, int(r[0]), int(r[1])))

    if name is not None:
        return Holiday(name, start_date, end_date, compensatory)
    return None


def parse_holiday_context(result: list):
    """根据传入的 year 以及 context 元祖数组 进行解析"""
    res = []
    for (year, context) in result:
        fts = re.split("[一二三四五六七八九十]、", context)
        holidays = []
        for f in fts:
            parse_res = parse_single_line(int(year), f)
            if parse_res is not None:
                holidays.append(parse_res)
        res.append((year, holidays))
    return res


def get_single_pub_content(holiday: dict, cache: list):
    """根据 节假日信息获取 节假日 html详情页面 \n
    如果本地已经存储了该页面则从本地读取文件返回文件内容 \n
    如果本地不存在，则从服务器获取html内容，并且将内容缓存后返回文件内容
    """
    articleid = holiday["articleid"]
    file_name = f"./holidays/{articleid}.html"

    if articleid in cache:
        with open(file_name, "r", encoding="utf-8") as text_file:
            return text_file.read()

    resp = get(holiday["url"])
    with open(file_name, "w", encoding="utf-8") as text_file:
        html_context = resp.content.decode("utf-8")
        text_file.write(html_context)
        return html_context


def get_holiday_context(holidays: list, cache: list):
    """获得节假日内容集合

    Args:
        holidays (list): 从 gov.cn 获取的节假日列表
        cache (list): 当前缓存的 列表

    Returns:
        [type]: [description]
    """
    result = []
    for holiday in holidays:
        res = get_single_pub_content(holiday, cache)
        res = BeautifulSoup(res, "html.parser")
        title = res.title.get_text()
        year = re.search(r"^国务院办公厅关于(\d{4})年.*$", title).group(1)
        haliday_context = res.select("#UCAP-CONTENT")[0].get_text()
        result.append((year, haliday_context))
    return result


def get_current_log_years():
    try:
        with open(ICS_FILE_NAME, "r", encoding="utf-8") as file:
            cal = Calendar(file.read())
            for line in cal.extra:
                if line.name == ICS_CURRENT_YEARS_LIST_NAME:
                    return line.value.split(",")
        return []
    except Exception:
        return []


def gen_ics_res_str(res: list[Tuple[str, list[Holiday]]]):
    """生成 ics 文件"""
    cal = Calendar()
    cal.extra.append(
        ContentLine(
            name=ICS_CURRENT_YEARS_LIST_NAME, value=",".join([r[0] for r in res])
        )
    )

    for (_, holidays) in res:
        for holiday in holidays:
            cal.events.add(
                Event(
                    name=holiday.holiday_name,
                    begin=holiday.holiday_start_date,
                    end=holiday.holiday_end_date,
                )
            )

    return str(cal)


def gen_json_res_str(res: list[Tuple[str, list[Holiday]]]):
    nres = []
    for r in res:
        nres.append({"year": r[0], "holidays": [item.__dict__() for item in r[1]]})
    return json.dumps(nres, default=str)


if __name__ == "__main__":
    res = get_holiday_context(get_gov_cn_holiday_resp(), get_holiday_cache())
    if set([r[0] for r in res]).issubset(set(get_current_log_years())):
        print("无新增节假日")
        sys.exit(0)
    result = parse_holiday_context(res)
    json_res, cal_res = gen_json_res_str(result), gen_ics_res_str(result)
    with open(ICS_FILE_NAME, "w", encoding="utf-8") as file:
        file.write(cal_res)
    with open(JSON_FILE_NAME, "w", encoding="utf-8") as file:
        file.write(json_res)
