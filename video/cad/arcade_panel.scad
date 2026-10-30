// Arcade control panel: a concept, UNVALIDATED.
//
// Nothing here has been printed, cut, fitted or tested. Every size is a named parameter and
// every default below is a placeholder, not a measurement: replace each one with the value
// measured on your own joysticks, buttons, encoder and table before using this for anything.
// The panel is a flat plate with holes; it carries no load-rated, food-contact or mains part.
//
// Open in OpenSCAD, set the parameters, F5 to preview, F6 to render.

/* [Panel: from your table, measured] */
panel_width = 600;        // placeholder: the near edge you have, in mm
panel_depth = 160;        // placeholder
panel_thickness = 6;      // placeholder: the sheet you will use
corner_radius = 8;        // placeholder

/* [Joysticks: from the joystick you buy, measured] */
players = 2;
joystick_shaft_hole = 30;     // placeholder: the hole the joystick's datasheet asks for
joystick_mount_spacing_x = 0; // placeholder: 0 leaves the mounting holes out until measured
joystick_mount_spacing_y = 0; // placeholder
joystick_mount_hole = 0;      // placeholder

/* [Buttons: from the buttons you buy, measured] */
buttons_per_player = 3;
button_hole = 28;         // placeholder: the hole the button's datasheet asks for
button_pitch = 40;        // placeholder: centre to centre
button_offset_x = 70;     // placeholder: first button from the joystick centre

/* [Layout] */
player_zone = panel_width / players;
row_y = panel_depth / 2;

echo("arcade_panel.scad: UNVALIDATED concept; every size is a placeholder until measured");

module plate() {
  linear_extrude(height = panel_thickness)
    offset(r = corner_radius) offset(delta = -corner_radius)
      square([panel_width, panel_depth]);
}

module player_holes(x0) {
  jx = x0 + player_zone * 0.3;
  translate([jx, row_y, -1]) cylinder(d = joystick_shaft_hole, h = panel_thickness + 2, $fn = 64);
  if (joystick_mount_hole > 0 && joystick_mount_spacing_x > 0 && joystick_mount_spacing_y > 0)
    for (sx = [-1, 1], sy = [-1, 1])
      translate([jx + sx * joystick_mount_spacing_x / 2, row_y + sy * joystick_mount_spacing_y / 2, -1])
        cylinder(d = joystick_mount_hole, h = panel_thickness + 2, $fn = 24);
  for (i = [0 : buttons_per_player - 1])
    translate([jx + button_offset_x + i * button_pitch, row_y, -1])
      cylinder(d = button_hole, h = panel_thickness + 2, $fn = 64);
}

difference() {
  plate();
  for (p = [0 : players - 1]) player_holes(p * player_zone);
}
