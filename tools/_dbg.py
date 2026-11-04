import sys, random
sys.path.insert(0,'tools'); sys.path.insert(0,'.')
import stuck_check as sc, tier_sim as ts, config
from engine.entities import Unit
from engine import movement
from engine.grid import BLOCKING
# wrap advance_unit / resolve_collisions to attribute entry
g_state={}
orig_adv=movement.advance_unit; orig_col=movement.resolve_collisions; orig_obs=movement.resolve_obstacles
def adv(u,dt,grid=None):
    p0=u.pos; orig_adv(u,dt,grid); g_state[u.id]=("advance",p0,u.pos,list(u.path)[:2])
movement.advance_unit=adv
import engine.world as W
W.movement.advance_unit=adv
random.seed(1)
defs=[ts.load_pokemon_def(str(sc.ROOT/r)) for r in config.ROSTER]
md=ts.load_map(str(sc.ROOT/config.DEFAULT_MAP)); world=ts.World(md.grid); match=ts.Match(world,md); match.vision=ts.FastVision(world.grid)
idx=random.sample(range(len(defs)),6)
for team in (0,1):
    lanes=ts.LANES[:]; random.shuffle(lanes)
    for lane,i in zip(lanes,idx[team*3:team*3+3]): ts._spawn(world,md,team,lane,defs[i])
match.assign_junglers(); match.vision.update(world,0); match.vision.update(world,1)
g=world.grid; prev={}; seen=set(); n=0
tick=0
while match.time<240 and n<8:
    before={e.id:(e.pos.x,e.pos.y) for e in world.entities.values() if isinstance(e,Unit)}
    match.update(config.TICK_DT,tick); tick+=1
    for e in world.entities.values():
        if isinstance(e,Unit) and e.alive and e.id not in seen and g.tile_at(int(e.pos.x//1),int(e.pos.y//1)) in BLOCKING:
            seen.add(e.id); n+=1
            st=g_state.get(e.id)
            print(type(e).__name__,e.id,"t=%.1f"%match.time,"before",before.get(e.id),"after",(e.pos.x,e.pos.y),"adv->",st[2] if st else None,"path",st[3] if st else None, "moving",e.moving)
