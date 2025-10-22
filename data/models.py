from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text

Base = declarative_base()

class Team(Base):
    __tablename__ = "teams"
    team_id = Column(Integer, primary_key=True)
    team_name = Column(String(255))
    player1 = Column(String(255))
    player2 = Column(String(255))
    group = Column(String(50))
    seed = Column(Integer)

class Match(Base):
    __tablename__ = "matches"
    match_id = Column(Integer, primary_key=True)
    group = Column(String(50))
    team1_id = Column(Integer)
    team2_id = Column(Integer)
    status = Column(String(50))
    set1_t1 = Column(Integer)
    set1_t2 = Column(Integer)
    set2_t1 = Column(Integer)
    set2_t2 = Column(Integer)
    set3_t1 = Column(Integer)
    set3_t2 = Column(Integer)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(Text)
