from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random as rnd
import math

# Initialize Ursina
app = Ursina()

# Window configuration
window.fullscreen = True
window.color = color.rgb(0, 200, 211)

# Constants
SUB_WIDTH = 16
NUM_SUBSETS = 16
TERRAIN_HEIGHT_SCALE = 24
OCTAVES = 4
FREQUENCY = 128
BLOCKS_PER_FRAME = 10  # Limit the number of blocks generated per frame

# Terrain Dictionary
terrain_dict = {}

# Perlin noise functions
def fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)

def lerp_color(a, b, t):
    return color.rgba(
        a.r + t * (b.r - a.r),
        a.g + t * (b.g - a.g),
        a.b + t * (b.b - a.b),
        a.a + t * (b.a - a.a)
    )

def grad(hash, x, y, z):
    h = hash & 15
    u = x if h < 8 else y
    v = y if h < 4 else z if h == 12 or h == 14 else x
    return ((u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v))

class PerlinNoise:
    def __init__(self, octaves=1, seed=0):
        self.octaves = octaves
        self.seed = seed
        self.permutation = [i for i in range(256)]
        rnd.seed(seed)
        rnd.shuffle(self.permutation)
        self.permutation += self.permutation

    def noise(self, x, y=0, z=0):
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        Z = int(math.floor(z)) & 255

        x -= math.floor(x)
        y -= math.floor(y)
        z -= math.floor(z)

        u = fade(x)
        v = fade(y)
        w = fade(z)

        A = self.permutation[X] + Y
        AA = self.permutation[A] + Z
        AB = self.permutation[A + 1] + Z
        B = self.permutation[X + 1] + Y
        BA = self.permutation[B] + Z
        BB = self.permutation[B + 1] + Z

        return lerp(w, lerp(v, lerp(u, grad(self.permutation[AA], x, y, z),
                                      grad(self.permutation[BA], x - 1, y, z)),
                              lerp(u, grad(self.permutation[AB], x, y - 1, z),
                                      grad(self.permutation[BB], x - 1, y - 1, z))),
                   lerp(v, lerp(u, grad(self.permutation[AA + 1], x, y, z - 1),
                                      grad(self.permutation[BA + 1], x - 1, y, z - 1)),
                              lerp(u, grad(self.permutation[AB + 1], x, y - 1, z - 1),
                                      grad(self.permutation[BB + 1], x - 1, y - 1, z - 1))))

    def __call__(self, coords):
        return self.noise(*coords)

# Perlin noise instance for terrain generation
noise = PerlinNoise(octaves=OCTAVES, seed=rnd.random())

# Load texture
block_texture = 'grass'  # Replace with your texture path

# Generating a block model
def generate_block(position, subset):
    print(f"Generating block at {position}")  # Debug statement
    subset.model.vertices.extend(cube_vertices(position))
    subset.model.uvs.extend([Vec2(0,0), Vec2(1,0), Vec2(1,1), Vec2(0,1)] * 6)
    subset.model.colors.extend([lerp_color(color.white, color.gray, rnd.random() * 0.3) for _ in range(6 * 4)])
    terrain_dict[str(position)] = 'T'
    subset.model.generate()

# Utility for 3D cube vertices
def cube_vertices(position):
    x, y, z = position
    return [
        Vec3(x,y,z), Vec3(x+1,y,z), Vec3(x+1,y+1,z), Vec3(x,y+1,z),
        Vec3(x+1,y,z), Vec3(x+1,y,z+1), Vec3(x+1,y+1,z+1), Vec3(x+1,y+1,z),
        Vec3(x+1,y,z+1), Vec3(x,y,z+1), Vec3(x,y+1,z+1), Vec3(x+1,y+1,z+1),
        Vec3(x,y,z+1), Vec3(x,y,z), Vec3(x,y+1,z), Vec3(x,y+1,z+1),
        Vec3(x,y+1,z), Vec3(x+1,y+1,z), Vec3(x+1,y+1,z+1), Vec3(x,y+1,z+1),
        Vec3(x,y,z+1), Vec3(x+1,y,z+1), Vec3(x+1,y,z), Vec3(x,y,z)
    ]

# Subset generation
class SwirlEngine:
    def __init__(self, sub_width):
        self.sub_width = sub_width
        self.run = 1
        self.iteration = 1
        self.count = 0
        self.position = Vec2(0, 0)
        self.current_direction = 0
        self.directions = [
            Vec2(0, 1),
            Vec2(1, 0),
            Vec2(0, -1),
            Vec2(-1, 0)
        ]

    def move(self):
        if self.count < self.run:
            self.position.x += self.directions[self.current_direction].x * self.sub_width
            self.position.y += self.directions[self.current_direction].y * self.sub_width
            self.count += 1
        else:
            self.change_direction()
            self.move()

    def change_direction(self):
        self.current_direction = (self.current_direction + 1) % 4
        if self.current_direction == 0 or self.current_direction == 2:
            self.run = self.iteration * 2 - 1
        else:
            self.run = self.iteration * 2
            if self.current_direction == 0:
                self.iteration += 1
        self.count = 0

    def reset(self, x, z):
        self.position = Vec2(x, z)
        self.run = 1
        self.iteration = 1
        self.count = 0
        self.current_direction = 0

# Mesh terrain class for terrain generation
class MeshTerrain(Entity):
    def __init__(self):
        super().__init__()
        self.subsets = [Entity(model=Mesh(), texture=block_texture) for _ in range(NUM_SUBSETS)]
        self.swirl_engine = SwirlEngine(sub_width=SUB_WIDTH)
        self.current_subset = 0
        self.generate_terrain_progress = 0  # Track progress of terrain generation within a frame
        self.generate = True  # Toggle terrain generation

    def generate_terrain(self):
        if not self.generate:
            return
        
        player_x = player.position.x
        player_z = player.position.z
        self.swirl_engine.reset(player_x, player_z)
        
        x = self.swirl_engine.position.x
        z = self.swirl_engine.position.y
        d = SUB_WIDTH // 2
        subset = self.subsets[self.current_subset]
        blocks_generated = 0

        print(f"Starting terrain generation at subset {self.current_subset} position ({x}, {z})")  # Debug statement

        for k in range(-d, d):
            for j in range(-d, d):
                pos = (floor(x + k), floor(noise([x + k / FREQUENCY, z + j / FREQUENCY]) * TERRAIN_HEIGHT_SCALE), floor(z + j))
                if str(pos) not in terrain_dict:
                    generate_block(pos, subset)
                    blocks_generated += 1
                    if blocks_generated >= BLOCKS_PER_FRAME:
                        print("Block generation limit reached for this frame.")  # Debug statement
                        return  # Exit function if block generation limit is reached

        self.swirl_engine.move()
        self.current_subset = (self.current_subset + 1) % NUM_SUBSETS
        print(f"Moved to subset {self.current_subset}")  # Debug statement

# Initialize count variable
count = 0

# Create terrain entity
terrain = MeshTerrain()

# Create player controller
player = FirstPersonController()

# Flight mode toggle
is_flying = False

# Simple update loop to generate terrain as the player moves
def update():
    global count, is_flying
    count += 1
    if count % 10 == 0:  # Update terrain generation every 10 frames
        print(f"Generating terrain at frame {count}")  # Debug statement
        terrain.generate_terrain()

    if held_keys['p']:
        is_flying = not is_flying
        if is_flying:
            player.gravity = 0
        else:
            player.gravity = 1

    if is_flying:
        if held_keys['space']:
            player.y += 5 * time.dt
        if held_keys['shift']:
            player.y -= 5 * time.dt

    if held_keys['h']:
        terrain.generate = not terrain.generate
        print(f"Terrain generation toggled: {terrain.generate}")

app.run()
