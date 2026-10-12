from .apex import Apex
from .athena import Athena
from .genesis import Genesis
from .northstar import Northstar
from .nova import Nova
from .omniview import Omniview
from .origin import Origin
from .prism import Prism
from .sentinel import Sentinel
from .titan import Titan

AGENTS = {a.name: a for a in (Origin(), Genesis(), Athena(), Nova(), Apex(),
                              Sentinel(), Titan(), Prism(), Northstar(), Omniview())}
