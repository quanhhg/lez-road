[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.932906,105.675112,20.978281,105.723417)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.932906,105.675112,20.978281,105.723417);
  node["barrier"](20.932906,105.675112,20.978281,105.723417);
);
(._; >>;);
out meta;
out count;
