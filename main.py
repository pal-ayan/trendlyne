from log import log
from datetime import datetime
from get_superstar_portfolio import exec


l = log()
l.log_info('***********START***********')

start_time = datetime.now()

try:
    e = exec(l)
    e.get_portfolio()
except:
    l.log_exception('Error')


time_diff = datetime.now() - start_time
l.log_info('***********END***********  ' + 'script completion took -> %s' % time_diff)