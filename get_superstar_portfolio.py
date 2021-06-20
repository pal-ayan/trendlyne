from selenium import webdriver as webdriver
from selenium.webdriver.common.by import By
import io
import os
import sqlite3 as sql
import threading
from datetime import date, datetime, timedelta
from threading import RLock
from time import sleep
from log import log
import re
from slack import WebClient
from selenium.webdriver.chrome.options import Options
from random import randint

class exec:

    def __init__(self, l):
        self.l = log() if l is None else l
        self.lock = RLock()
        self._insert_statement = '''
                            insert into data (
                                Investor,
                                Company,
                                HoldingValue,
                                Shares,
                                Status
                            ) values (
                                '%(investor)s',
                                '%(company)s',
                                '%(holding)s',
                                '%(shares)s',
                                '%(status)s'
                            )
                            '''

        self._select_statement = '''
                            select
                                Investor,
                                Company,
                                HoldingValue,
                                Shares,
                                Status 
                            from data where
                                Investor = '%(investor)s'
                                and Company = '%(company)s'
                            '''

    def send_slack_message(self, text):
        pass
        # Create a slack client
        #slack_web_client = WebClient('xoxb-1098430611776-2188401731570-MjAwmIosnHhpgSETFlApgfSr')
        #slack_web_client.chat_postMessage(channel='trendlyne', text=text)

    def acquire_lock(self):
        self.l.log_debug('attempting to acquire lock')
        self.lock.acquire(blocking=True)
        self.l.log_debug('lock acquired')

    def release_lock(self):
        self.lock.release()
        self.l.log_debug('lock released')

    def execute_sql(self, statement, commit=False, db=os.path.realpath('.') + '/db/superstar.db'):
            ls_results = []
            retry_count = 0
            self.acquire_lock()
            conn = sql.connect(db, isolation_level='EXCLUSIVE')
            self.l.log_debug(statement)
            while True:
                try:
                    results = conn.execute(statement)
                    for result in results:
                        ls_results.append(result)
                    break
                except sql.OperationalError as e:
                    self.l.log_exception('Error Occured while executing statement -> ' + statement)
                    if retry_count >= 10:
                        self.l.log_error('maximum retry reached for statement -> ' + statement)
                        self.release_lock()
                        raise Exception('maximum retry reached for statement -> ' + statement)
                    sleep(0.5)
                    retry_count += 1
                    continue
            if commit:
                self.l.log_debug('committing')
                conn.commit()
            conn.close()
            self.release_lock()
            return ls_results

    def get_portfolio(self):
        try:
            options = webdriver.ChromeOptions()
            options.headless = True

            wd = webdriver.Chrome(os.path.realpath('.') + '/chromedriver.exe', options=options)

            wd.get("https://trendlyne.com/portfolio/superstar-shareholders/index/individual/#")

            wd.find_element_by_xpath("//button[@aria-label='Close']").click()

            sleep(randint(5,60))

            wd.find_element_by_xpath("//select[@name='groupTable_length']/option[text()='100']").click()

            table_id = wd.find_element(By.ID, 'groupTable_wrapper')
            rows = table_id.find_elements(By.TAG_NAME, "tr") # get all of the rows in the table
            self.l.log_info('Processing - '+str(len(rows))+' rows')
            ls_processed_investors = []
            for row in rows:
                r = row.get_attribute('role')
                c = row.get_attribute('class')
                if r == 'row' and c not in {'odd', 'even'}:
                    continue
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >0:
                    col = cols[0]
                    investor = col.text
                    if investor in ls_processed_investors:
                        self.l.log_info('already processed - '+investor)
                        continue
                    self.l.log_info('Portfolio of - '+investor)
                    elm = wd.find_element_by_partial_link_text(investor)
                    link = elm.get_attribute('href')
                    wd.execute_script("window.open('');")
                    wd.switch_to.window(wd.window_handles[1])
                    wd.get(link)

                    sub_table_id = wd.find_element(By.ID, 'DataTables_Table_0_wrapper')
                    sub_rows = sub_table_id.find_elements(By.TAG_NAME, "tr")
                    for sub_row in sub_rows:
                        # Get the columns (all the column 2
                        sub_cols = sub_row.find_elements(By.TAG_NAME, "td")
                        if len(sub_cols) >0:
                            company_name = sub_cols[1].text
                            company_name = company_name.replace('\n+','')
                            company_name = company_name.replace("'", "''")
                            holding_value = sub_cols[3].text
                            quantity = sub_cols[4].text
                            change = sub_cols[5].text
                            self.l.log_info("company name - "+company_name)
                            self.l.log_info("HoldingValue - "+holding_value)
                            self.l.log_info("quantity - "+quantity)
                            self.l.log_info("change - "+change)

                            regexp = re.compile(r'[a-zA-Z]')
                            if regexp.search(change):
                                status = change
                            else:
                                status = 'N/A'

                            quantity = quantity.replace(',', '').strip()
                            quantity = quantity.replace('-','').strip()
                            if len(quantity) == 0:
                                quantity = 0


                            substitution_dict = {
                                'investor': investor,
                                'company': company_name,
                                'holding': holding_value,
                                'shares': quantity,
                                'status': status
                            }

                            statement = self._select_statement % substitution_dict

                            results = self.execute_sql(statement, False)

                            if len(results) > 0:
                                for result in results:
                                    #i = result[0]
                                    #c = result[1]
                                    h = result[2]
                                    sh = result[3]
                                    st = result[4]

                                    if holding_value != h:
                                        self.l.log_info(investor + ' - Holding Value of '+ company_name + ' has changed from '+str(h)+ ' to '+holding_value)
                                        self.send_slack_message(investor + ' - Holding Value of '+ company_name + ' has changed from '+str(h)+ ' to '+holding_value)
                                        u_statement = '''
                                            update data set HoldingValue = '%(holding)s' where Investor = '%(investor)s' and Company = '%(company)s'
                                        ''' % substitution_dict
                                        self.execute_sql(u_statement, True)
                                    else:
                                        self.l.log_info('No updates to holding value for - '+investor+' - for the company'+company_name)

                                    if int(quantity) != sh:
                                        self.l.log_info(investor + ' - quantity of '+ company_name + ' has changed from '+str(sh)+ ' to '+quantity)
                                        self.send_slack_message(investor + ' - quantity of '+ company_name + ' has changed from '+str(sh)+ ' to '+quantity)
                                        u_statement = '''
                                            update data set Shares = '%(shares)s' where Investor = '%(investor)s' and Company = '%(company)s'
                                        ''' % substitution_dict
                                        self.execute_sql(u_statement, True)
                                    else:
                                        self.l.log_info('No updates to quantity for - ' + investor + ' - for the company' + company_name)

                                    if status != st:
                                        self.l.log_info(investor + ' - status of '+ company_name + ' has changed from '+str(st)+ ' to '+status)
                                        self.send_slack_message(investor + ' - status of '+ company_name + ' has changed from '+str(st)+ ' to '+status)
                                        u_statement = '''
                                            update data set Status = '%(status)s' where Investor = '%(investor)s' and Company = '%(company)s'
                                        ''' % substitution_dict
                                        self.execute_sql(u_statement, True)
                                    else:
                                        self.l.log_info('No updates to status for - ' + investor + ' - for the company' + company_name)
                            else:
                                self.l.log_info('Inserting new data for '+investor+ ' and company - '+company_name)
                                self.send_slack_message('Inserting new data for '+investor+ ' and company - '+company_name)
                                i_statement = self._insert_statement % substitution_dict
                                self.execute_sql(i_statement, True)

                    wd.close()

                    # Switching to old tab
                    wd.switch_to.window(wd.window_handles[0])
                    ls_processed_investors.append(investor)
        except:
            self.l.log_exception('Error')
            self.send_slack_message('Error Occured')




