[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.751026,105.914438,20.796465,105.962752)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.751026,105.914438,20.796465,105.962752);
  node["barrier"](20.751026,105.914438,20.796465,105.962752);
);
(._; >>;);
out meta;
out count;
