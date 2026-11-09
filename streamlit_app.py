import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title='달러 세븐스플릿 V2.1', page_icon='💵', layout='wide')
KST=ZoneInfo('Asia/Seoul')
st.title('💵 달러 세븐스플릿 V2.1')
st.caption('USD/KRW=Twelve Data, DXY=Yahoo Finance · 09:00/11:00/15:30 자동 복원')
st.warning('투자 판단 보조용입니다. 실제 체결환율과 수수료는 별도로 확인하세요.')

def key():
    try:return st.secrets.get('TWELVE_DATA_API_KEY','')
    except:return os.getenv('TWELVE_DATA_API_KEY','')

def kst(df):
    ix=pd.DatetimeIndex(df.index)
    if ix.tz is None: ix=ix.tz_localize('UTC')
    df.index=ix.tz_convert(KST); return df.sort_index()

def nearest(df,t,limit=20):
    if df.empty:return None
    i=df.index.get_indexer([t],method='nearest')[0]
    if i<0 or abs(df.index[i]-t)>pd.Timedelta(minutes=limit):return None
    r=df.iloc[i]; v=r.get('Close',r.get('close'))
    if isinstance(v,pd.Series):v=v.iloc[0]
    return {'close':float(v),'actual':df.index[i]}

@st.cache_data(ttl=120,show_spinner=False)
def dxy_data():
    d=yf.download('DX-Y.NYB',period='5d',interval='1m',progress=False,auto_adjust=False,threads=False)
    if d.empty:raise RuntimeError('DXY 1분봉 조회 실패')
    if isinstance(d.columns,pd.MultiIndex):d.columns=[x[0] for x in d.columns]
    return kst(d)

@st.cache_data(ttl=120,show_spinner=False)
def krw_data(api):
    r=requests.get('https://api.twelvedata.com/time_series',params={'symbol':'USD/KRW','interval':'1min','outputsize':5000,'timezone':'Asia/Seoul','apikey':api},timeout=30)
    r.raise_for_status(); j=r.json()
    if j.get('status')=='error':raise RuntimeError(j.get('message','Twelve Data 오류'))
    d=pd.DataFrame(j.get('values',[]))
    if d.empty:raise RuntimeError('USD/KRW 1분봉 조회 실패')
    d['datetime']=pd.to_datetime(d['datetime']); d=d.set_index('datetime').sort_index(); d.index=d.index.tz_localize(KST)
    for c in ['open','high','low','close']:d[c]=pd.to_numeric(d[c],errors='coerce')
    return d

def direction(x,th):
    return '상승 🔴' if x>=th else ('하락 🔵' if x<=-th else '보합 ⚪')
def gap(a,b,th):
    x,y=direction(a,th),direction(b,th)
    if x=='상승 🔴' and y in ('하락 🔵','보합 ⚪'):return '하방 🔵'
    if x in ('하락 🔵','보합 ⚪') and y=='상승 🔴':return '상방 🔴'
    return '혼조/중립 ⚪'

M={
('하방 🔵','하방 🔵','적정'):('A+',100),('혼조/중립 ⚪','하방 🔵','적정'):('A',100),('상방 🔴','하방 🔵','적정'):('B+',70),('하방 🔵','혼조/중립 ⚪','적정'):('B',50),('혼조/중립 ⚪','혼조/중립 ⚪','적정'):('C',0),('상방 🔴','혼조/중립 ⚪','적정'):('C-',0),('하방 🔵','상방 🔴','적정'):('D',0),('혼조/중립 ⚪','상방 🔴','적정'):('D',0),('상방 🔴','상방 🔴','적정'):('F',0),
('하방 🔵','하방 🔵','초과'):('B',50),('혼조/중립 ⚪','하방 🔵','초과'):('C+',30),('상방 🔴','하방 🔵','초과'):('C',0),('하방 🔵','혼조/중립 ⚪','초과'):('C-',0),('혼조/중립 ⚪','혼조/중립 ⚪','초과'):('관망',0),('상방 🔴','혼조/중립 ⚪','초과'):('D',0),('하방 🔵','상방 🔴','초과'):('F',0),('혼조/중립 ⚪','상방 🔴','초과'):('F',0),('상방 🔴','상방 🔴','초과'):('F',0)}

if 'market_data' not in st.session_state:st.session_state.market_data=None
with st.sidebar:
    amount0=st.number_input('1차수 기본금액(원)',10000,value=100000,step=10000)
    th=st.number_input('방향 임계값(%)',0.01,2.0,0.10,0.01)
    buf=st.number_input('적정환율 완충폭(%)',0.0,5.0,0.30,0.05)
    morning=st.time_input('오전 기준시각',time(11,0)); final=st.time_input('마감 기준시각',time(15,30))
    day=st.date_input('조회 날짜',datetime.now(KST).date())

api=key()
if not api:
    st.error('Streamlit Secrets에 TWELVE_DATA_API_KEY를 등록하세요.')
else:
    if st.button('📡 오늘 데이터 자동 불러오기',type='primary',use_container_width=True):
        try:
            with st.spinner('시세 자동 조회 중...'):
                kd=krw_data(api); dd=dxy_data()
                ts={'start':datetime.combine(day,time(9),tzinfo=KST),'morning':datetime.combine(day,morning,tzinfo=KST),'final':datetime.combine(day,final,tzinfo=KST)}
                res={'DXY':{},'USD/KRW':{}}
                for n,t in ts.items():
                    res['DXY'][n]=nearest(dd,t);res['USD/KRW'][n]=nearest(kd,t)
                st.session_state.market_data=res
                for n in ts:
                    if res['DXY'][n]:st.session_state['dxy_'+n]=res['DXY'][n]['close']
                    else:st.session_state.pop('dxy_'+n,None)
                    if res['USD/KRW'][n]:st.session_state['krw_'+n]=res['USD/KRW'][n]['close']
                    else:st.session_state.pop('krw_'+n,None)
            st.rerun()
        except Exception as e:st.error(f'자동조회 실패: {e}')

md=st.session_state.market_data
st.subheader('① 자동 조회값 및 수동 보정')
vals={'DXY':{},'USD/KRW':{}}
for n,label in [('start','09:00 시작'),('morning',morning.strftime('%H:%M')+' 오전'),('final',final.strftime('%H:%M')+' 마감')]:
    st.markdown('#### '+label);a,b=st.columns(2)
    x=md['DXY'].get(n) if md else None;y=md['USD/KRW'].get(n) if md else None
    with a:
        vals['DXY'][n]=st.number_input('DXY '+label,min_value=0.0,value=float(x['close']) if x else 0.0,step=.001,format='%.4f',key='dxy_'+n)
        st.caption('✅ 자동 선택: '+x['actual'].strftime('%Y-%m-%d %H:%M:%S KST') if x else '❌ 자동값 없음 · 수동입력')
    with b:
        vals['USD/KRW'][n]=st.number_input('USD/KRW '+label,min_value=0.0,value=float(y['close']) if y else 0.0,step=.1,format='%.4f',key='krw_'+n)
        st.caption('✅ 자동 선택: '+y['actual'].strftime('%Y-%m-%d %H:%M:%S KST') if y else '❌ 자동값 없음 · 수동입력')

st.subheader('② 최종 판정')
if st.button('판정 실행',type='primary',use_container_width=True):
    d0,d1,d2=[vals['DXY'][x] for x in ('start','morning','final')];k0,k1,k2=[vals['USD/KRW'][x] for x in ('start','morning','final')]
    if min(d0,d1,d2,k0,k1,k2)<=0:st.error('6개 시세 중 누락값이 있습니다. 자동조회 또는 수동입력 후 실행하세요.');st.stop()
    dp1=(d1/d0-1)*100;kp1=(k1/k0-1)*100;dp2=(d2/d0-1)*100;kp2=(k2/k0-1)*100
    g1,g2=gap(dp1,kp1,th),gap(dp2,kp2,th);fair=k0*d2/d0
    if k2<fair*(1-buf/100):shown,keyp='적정 (싸다)','적정'
    elif k2>fair*(1+buf/100):shown,keyp='초과 (비쌈)','초과'
    else:shown,keyp='중립','초과'
    grade,w=M[(g1,g2,keyp)];amt=round(amount0*w/100);usd=amt/k2 if amt else 0
    c1,c2,c3,c4=st.columns(4);c1.metric('오전 갭',g1);c2.metric('마감 갭',g2);c3.metric('적정환율',f'{fair:,.2f}원');c4.metric('가격 판정',shown)
    st.markdown(f'## 판정: **{grade}**');st.markdown(f'### 1차수 적용 비중 **{w}%** · 판정금액 **{amt:,}원**')
    st.info(f'예상 매수량: 약 {usd:,.2f} USD' if amt else '신규 매수 관망 판정')
